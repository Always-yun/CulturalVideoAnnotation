"""
文化符号候选检索器（创新点2：多模态检索 → Top-K 文化候选）

设计说明
--------
本期（按导师意见升级阶段）检索链路只"定义接口、预留插槽"，标注主管线默认使用
NullCulturalRetriever（不检索、不改变现有行为）。

接口已按"多模态"形态设计：检索输入 video_context 同时承载
  - scene_text：视频关键帧经 VLM 生成的场景描述（视觉→文本的桥梁）
  - keywords ：抽帧 OCR / 标签词
  - video_path / frame_paths：原始视频与关键帧路径
未来实现真正的多模态检索时，只需新增一个子类（例如 CLIPCulturalRetriever），对
知识库 reference_images 与视频关键帧做统一图像 embedding 近邻检索，
均无需改动 PromptManager / InferenceEngine 的调用签名。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .symbol_kb import SymbolKnowledgeBase


@dataclass
class CulturalCandidate:
    """单个 Top-K 文化候选"""
    symbol_id: str
    canonical_name: str
    cultural_dimension: str       # 新五维（可能含 ; 多标签）
    dimension_code: str           # ANCIENT/RED/FOLK/TECH/MODERN
    score: float = 0.0
    reason: str = ""              # 命中依据（如"别名命中：紫禁城"）
    # 创新点2第三阶段：多模态检索分项分数（不覆盖 score，供追溯与评测）
    image_score: float = 0.0      # CLIP 图像端相似度（归一化到 [0,1]）
    text_score: float = 0.0       # 关键词/文本检索原始分数（归一化到 [0,1]）
    fusion_score: float = 0.0     # 图像+文本融合分数（最终排序依据）
    raw: Dict[str, Any] = field(default_factory=dict)

    ranking_score: Optional[float] = None
    retrieval_evidence: Dict[str, Any] = field(default_factory=dict)

    def to_symbol_dict(self) -> Dict[str, Any]:
        """兼容 SymbolKnowledgeBase.format_candidates 所需的符号字典"""
        return self.raw or {
            "symbol_id": self.symbol_id,
            "canonical_name": self.canonical_name,
            "cultural_dimension": self.cultural_dimension,
            "dimension_code": self.dimension_code,
        }


class BaseCulturalRetriever(ABC):
    """文化符号检索器抽象接口（多模态可插拔）"""

    @abstractmethod
    def retrieve(self, video_context: Optional[Dict[str, Any]] = None,
                 top_k: int = 5, region: Optional[str] = None,
                 dimension: Optional[str] = None) -> List[CulturalCandidate]:
        """
        Args:
            video_context: {'scene_text': str, 'keywords': List[str],
                            'video_path': str, 'frame_paths': List[str]}
            top_k: 返回候选数
            region: 限定地域子集（如 "北京"）
            dimension: 限定文化维度
        Returns:
            Top-K CulturalCandidate 列表，按相关度降序
        """
        raise NotImplementedError


class NullCulturalRetriever(BaseCulturalRetriever):
    """空检索器：默认使用，返回空候选，保持标注管线现有行为不变"""

    def retrieve(self, video_context=None, top_k=5, region=None, dimension=None):
        return []


def extract_cultural_query(kb: SymbolKnowledgeBase,
                           scene_text: str) -> List[str]:
    """从 VLM 视觉描述中提取"文化 Query"关键词（创新点2链路第三步）。

    确定性规则：用知识库词表（规范名+别名+关键词）在描述文本上做子串扫描，
    命中的词即视为文化 Query。不依赖任何模型，可追溯、可复现。
    返回按出现顺序去重后的词表（供日志/追踪与检索器 keywords 字段使用）。
    """
    if not scene_text:
        return []
    text_lower = scene_text.lower()
    seen, keywords = set(), []
    for s in kb.symbols:
        for term in kb.expand_terms(s):
            t = term.strip()
            if len(t) < 2:
                continue
            tl = t.lower()
            if tl in text_lower and tl not in seen:
                seen.add(tl)
                keywords.append(t)
    return keywords


class KeywordCulturalRetriever(BaseCulturalRetriever):
    """确定性关键词检索兜底（无需模型/向量库）。

    用 video_context 中的 scene_text / keywords 在知识库规范名、别名、
    关键词、视觉特征上做加权匹配。适合离线调试与无 GPU 环境。
    多模态向量检索启用后，本类可作为回退（fallback）方案。
    """

    def __init__(self, kb: Optional[SymbolKnowledgeBase] = None):
        self.kb = kb or SymbolKnowledgeBase()

    def retrieve(self, video_context=None, top_k=5, region=None, dimension=None):
        video_context = video_context or {}
        query_parts = []
        if video_context.get("scene_text"):
            query_parts.append(str(video_context["scene_text"]))
        kws = video_context.get("keywords") or []
        if isinstance(kws, (list, tuple)):
            query_parts.extend(str(k) for k in kws)
        else:
            query_parts.append(str(kws))
        query_text = " ".join(p for p in query_parts if p)

        # 地域过滤：若显式指定 region 且与当前库不同，则临时加载该子集
        kb = self.kb
        if region and self.kb._meta.get("experiment_region") != region:
            kb = SymbolKnowledgeBase(region=region)

        candidates = []
        for score, matched_terms, s in kb.search_scored(query_text, top_k=top_k,
                                                        dimension=dimension):
            # 命中词去重（保持出现顺序），避免规范名/别名/关键词重复计入依据
            seen_terms, uniq_terms = set(), []
            for t in matched_terms:
                if t not in seen_terms:
                    seen_terms.add(t)
                    uniq_terms.append(t)
            reason = "关键词/别名命中：" + "、".join(uniq_terms[:5]) if uniq_terms \
                else "关键词/别名匹配"
            candidates.append(CulturalCandidate(
                symbol_id=s.get("symbol_id", ""),
                canonical_name=s.get("canonical_name", ""),
                cultural_dimension=s.get("cultural_dimension", ""),
                dimension_code=s.get("dimension_code", ""),
                score=float(score),
                reason=reason,
                text_score=float(score),
                fusion_score=float(score),  # 纯文本检索：fusion = text
                raw=s,
            ))
        return candidates
