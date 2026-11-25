"""文化符号图像检索与文本分数融合。

真实图片必须同时有本地文件、显式启用标记和已审核状态。
默认不使用文本向量代替参考图片；纯Image候选池只来自图像分数。
视频4帧和实体参考图分别均值聚合、L2归一化，以余弦相似度检索；
融合分数为alpha * normalized_text + (1-alpha) * image_score。
"""

import os
from typing import Any, Dict, List, Optional

import torch

from .symbol_kb import SymbolKnowledgeBase
from .retriever import (
    BaseCulturalRetriever,
    CulturalCandidate,
    KeywordCulturalRetriever,
    extract_cultural_query,
)
from .clip_encoder import CLIPEncoder


class MultimodalCulturalRetriever(BaseCulturalRetriever):
    """CLIP 图像检索 + 关键词文本检索融合的多模态检索器

    Args:
        kb: 知识库
        clip_encoder: CLIP 编码器（None 时懒加载）
        top_k: 默认候选数
        fusion_alpha: 文本分数权重（0~1），图像权重 = 1 - alpha
        num_frames: 视频关键帧采样数
    """

    def __init__(self,
                 kb: Optional[SymbolKnowledgeBase] = None,
                 clip_encoder: Optional[CLIPEncoder] = None,
                 fusion_alpha: float = 0.5,
                 num_frames: int = 4,
                 image_text_fallback: bool = False, ranking_strategy: str = "legacy"):
        """
        Args:
            kb: 知识库
            clip_encoder: CLIP 编码器（None 时懒加载）
            top_k: 默认候选数
            fusion_alpha: 文本分数权重（0~1），图像权重 = 1 - alpha
            num_frames: 视频关键帧采样数
            image_text_fallback: 无真实参考图时是否用文本描述编码兜底。
                Image 检索实验默认关闭（False）：无参考图的符号图像分记为 0，
                并在 image_evidence_status 中标记 unavailable，避免用文本模拟图像检索。
        """
        if ranking_strategy not in {"legacy", "evidence_v1"}:
            raise ValueError("Unknown ranking strategy")
        self.ranking_strategy = ranking_strategy
        self.kb = kb or SymbolKnowledgeBase()
        self._clip = clip_encoder  # 懒加载
        self.fusion_alpha = fusion_alpha
        self.num_frames = num_frames
        self.image_text_fallback = image_text_fallback
        # 复用关键词检索器做文本端
        self._keyword_retriever = KeywordCulturalRetriever(self.kb)
        # 知识库符号参考 embedding 缓存（首次检索时预计算）
        self._ref_embeddings: Optional[torch.Tensor] = None
        self._ref_symbols: List[Dict[str, Any]] = []
        # 图像证据不可得（无可用真实参考图）的符号集合
        self.image_unavailable_symbols: set = set()

    @property
    def clip(self) -> CLIPEncoder:
        if self._clip is None:
            self._clip = CLIPEncoder()
        return self._clip

    # ------------------------------------------------------------------ #
    # 知识库参考 embedding 预计算
    # ------------------------------------------------------------------ #
    def _build_reference_embeddings(self) -> None:
        """预计算已审核且启用的参考图；文本兜底仅在显式开启时使用。"""
        kb_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        texts, image_paths, symbol_indices = [], [], []

        for idx, s in enumerate(self.kb.symbols):
            # 1. 优先检查 reference_images 是否有有效本地图片路径
            from .reference_policy import eligible_reference_paths
            valid_images = eligible_reference_paths(s, kb_root)
            if valid_images:
                # 用真实参考图做图像编码（图像-图像检索的唯一合法来源）
                img_emb = self.clip.encode_images(valid_images)
                pooled = img_emb.mean(dim=0)
                pooled = pooled / pooled.norm().clamp(min=1e-8)
                symbol_indices.append((idx, pooled))
            elif self.image_text_fallback:
                # 文本兜底（仅在显式开启时使用，默认关闭以避免用文本模拟图像检索）
                desc = " ".join(filter(None, [
                    s.get("canonical_name", ""),
                    s.get("visual_features", ""),
                    s.get("cultural_description", ""),
                    s.get("typical_scene", ""),
                ]))
                texts.append((idx, desc))
            else:
                # 无真实参考图 → 图像证据不可得，图像分保持缺失（不伪造）
                self.image_unavailable_symbols.add(str(s.get("symbol_id", "")))

        # 批量文本编码
        if texts:
            idx_list, text_list = zip(*texts)
            text_embs = self.clip.encode_text(list(text_list))
            for i, idx in enumerate(idx_list):
                symbol_indices.append((idx, text_embs[i]))

        # 按符号顺序组装
        symbol_indices.sort(key=lambda x: x[0])
        self._ref_symbols = [self.kb.symbols[idx] for idx, _ in symbol_indices]
        self._ref_embeddings = torch.stack([emb for _, emb in symbol_indices]) \
            if symbol_indices else torch.zeros(0, 0)
        print(f"--- 知识库参考 embedding 预计算完成: {len(self._ref_symbols)} 个符号 "
              f"(维度={self._ref_embeddings.shape}) ---")

    # ------------------------------------------------------------------ #
    # 检索主入口
    # ------------------------------------------------------------------ #
    def retrieve(self, video_context: Optional[Dict[str, Any]] = None,
                 top_k: int = 5, region: Optional[str] = None,
                 dimension: Optional[str] = None) -> List[CulturalCandidate]:
        video_context = video_context or {}
        video_path = video_context.get("video_path", "")

        # 1. 预计算知识库参考 embedding
        if self._ref_embeddings is None:
            self._build_reference_embeddings()

        # 2. 视频关键帧 → CLIP 图像 embedding
        image_scores = {}  # symbol_id → image_score
        if self._ref_embeddings.shape[0] > 0 and video_path and os.path.exists(video_path):
            video_emb = self.clip.encode_frames_from_video(video_path,
                                                            num_frames=self.num_frames)
            if self._ref_embeddings.shape[0] > 0 and video_emb.norm() > 0:
                sims = (self._ref_embeddings @ video_emb).tolist()
                for i, s in enumerate(self._ref_symbols):
                    # CLIP 余弦相似度 ∈ [-1,1]，归一化到 [0,1]
                    image_scores[s["symbol_id"]] = (sims[i] + 1.0) / 2.0

        return self.rank_with_scores(video_context, image_scores, top_k, region, dimension)

    def rank_with_scores(self, video_context, image_scores, top_k=5, region=None, dimension=None):
        """用已保存或实时完整图像分数重排；可离线配对验证而无需重新调用VLM。"""
        # 3. 文本检索分数（复用 KeywordCulturalRetriever）
        scene_text = video_context.get("scene_text", "")
        keywords = video_context.get("keywords") or extract_cultural_query(self.kb, scene_text)
        text_candidates = self._keyword_retriever.retrieve(
            {"scene_text": scene_text, "keywords": keywords},
            top_k=len(self.kb),  # 全量打分后取 top_k
            region=region, dimension=dimension)
        text_score_map = {c.symbol_id: c.score for c in text_candidates}
        # 文本分数归一化到 [0,1]
        max_text = max(text_score_map.values()) if text_score_map else 1.0
        if max_text <= 0:
            max_text = 1.0

        # 4. 融合：对每个知识库符号计算 image_score / text_score / fusion_score
        all_ids = (set(image_scores) if self.fusion_alpha == 0 else
                   set(image_scores) | set(text_score_map))
        scored: List[CulturalCandidate] = []
        for sid in all_ids:
            symbol = self.kb.get(sid) or {}
            t_score = text_score_map.get(sid, 0.0) / max_text
            i_score = image_scores.get(sid, 0.0)
            fusion = self.fusion_alpha * t_score + (1 - self.fusion_alpha) * i_score
            # reason 继承关键词检索的命中依据
            kw_cand = next((c for c in text_candidates if c.symbol_id == sid), None)
            reason = kw_cand.reason if kw_cand else "图像相似度匹配"
            scored.append(CulturalCandidate(
                symbol_id=sid,
                canonical_name=symbol.get("canonical_name", ""),
                cultural_dimension=symbol.get("cultural_dimension", ""),
                dimension_code=symbol.get("dimension_code", ""),
                score=fusion,  # 最终排序分数 = 融合分数
                reason=reason,
                image_score=round(i_score, 4),
                text_score=round(t_score, 4),
                fusion_score=round(fusion, 4),
                raw=symbol,
            ))

        if self.ranking_strategy == "evidence_v1":
            from .evidence_ranking import EvidenceRanker
            return EvidenceRanker(self.kb).rerank(video_context, image_scores, scored, top_k, region, dimension, self.fusion_alpha)

        # 5. 按融合分数降序取 Top-K
        scored.sort(key=lambda c: (-c.score, c.symbol_id))
        return scored[:top_k]
