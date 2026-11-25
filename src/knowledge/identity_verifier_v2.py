"""身份级证据核验模块 v2（Identity Evidence Verification Module）

设计要点（针对 v1 的过拒问题）：
1. 证据分层：Strong Identity Evidence / Supporting Evidence / Category-Hierarchy Evidence。
   - 父实体命中（如 神武门 → 故宫）只属于 Category-Hierarchy，绝不等于 exact identity。
2. 文本身份通道与视觉身份通道并列：
   - Text Identity Channel：canonical / alias / OCR / 明确实体提及
   - Visual Identity Channel：参考图匹配（max / top-k / 多帧一致性）+ 独特视觉属性
   文本没出现候选名称 **不再** 直接拒识；若视觉通道强，仍可进入 accept 判断。
3. 规则初筛决定 verification_required，只有模糊样本才进入 LLM 二次核验（省调用）。
4. 视觉阈值来自 validation set 标定（config/identity_verifier_v2.json），不在 test 上调整。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import torch

from .identity_evidence_gate import IdentityEvidenceGate, _focus_text, _terms
from .symbol_kb import SymbolKnowledgeBase

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "identity_verifier_v2.json"
KEYFRAME_DIR = _PROJECT_ROOT / 'experiments/innovation2/cache/final31_keyframes'

STATUS_ACCEPT = "accept_exact_identity"
STATUS_RELATED = "reject_related_but_not_exact"
STATUS_INSUFFICIENT = "reject_insufficient_evidence"

VERIFIER_SYSTEM_PROMPT = """你是「文化符号身份核验器」。你的唯一任务是判断：给定视频证据能否证明某个候选文化符号与视频中的具体文化实体是**同一身份**。

严格规则（必须遵守）：
1. 视觉/语义**高相似不等于同一身份**。
2. **父实体命中不等于子实体身份**（画面属于故宫建筑群，不等于视频实体就是「故宫」这一候选本身）。
3. **子实体命中不等于父实体身份**。
4. **同景区、同建筑群、同区域不等于同一文化符号**。
5. **同类别、同文化维度、同建筑类型不等于同一文化符号**。
6. 必须优先寻找**身份级证据**：候选规范名/别名的明确出现、画面中候选专属文字标识（匾额、题字、铭牌、OCR 可读字样）、候选专属且独特的视觉特征、与候选参考图的高置信匹配。
7. 证据不足时必须拒绝，**不允许猜测**，不允许用「看起来像」代替身份证据。
8. 反过来，**不能因为场景描述里没出现候选名称就自动拒绝**：如果视觉证据（多帧稳定匹配候选参考图、独特结构特征）足够强，仍可接受。
9. 只有确认 exact identity 才能输出 accept_exact_identity。
10. 只要证据表明是相关实体（父/子/同景区/同类/相似），必须输出 reject_related_but_not_exact。

只输出一个 JSON 对象，不要输出任何其他文字：
{
  "candidate": "候选规范名",
  "identity_status": "accept_exact_identity | reject_related_but_not_exact | reject_insufficient_evidence",
  "text_identity_evidence": "文本身份证据，无则写 none",
  "visual_identity_evidence": "视觉身份证据，无则写 none",
  "hierarchy_relation": "none | parent_entity | child_entity | same_scenic_area | same_category | similar_entity",
  "reason": "简要理由",
  "confidence": 0.0
}"""


# --------------------------------------------------------------------------- #
# 关键帧抽取（同时供 CLIP 与 Verifier 使用）
# --------------------------------------------------------------------------- #
def extract_keyframes(video_path: str, video_id: str, num_frames: int = 4) -> List[str]:
    """均匀采样关键帧并落盘，返回图片路径列表。"""
    import cv2
    from PIL import Image

    out_dir = KEYFRAME_DIR / str(video_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = sorted(out_dir.glob("frame_*.jpg"))
    if len(paths) >= num_frames:
        return [str(p) for p in paths[:num_frames]]

    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    paths: List[str] = []
    if total:
        for i in range(num_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(i * total / num_frames))
            ok, frame = cap.read()
            if not ok:
                continue
            p = out_dir / f"frame_{i}.jpg"
            Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).save(p, quality=90)
            paths.append(str(p))
    cap.release()
    return paths


# --------------------------------------------------------------------------- #
# 视觉身份索引：每个候选的参考图逐图 embedding
# --------------------------------------------------------------------------- #
class VisualIdentityIndex:
    """KB 参考图的逐图 CLIP embedding，用于逐帧视觉身份证据计算。"""

    def __init__(self, kb: SymbolKnowledgeBase, clip_encoder, project_root: Path = _PROJECT_ROOT):
        self.kb = kb
        self.clip = clip_encoder
        self.project_root = project_root
        self.symbol_ids: List[str] = []
        self._ref_embs: Dict[str, torch.Tensor] = {}
        self._build()

    def _resolve(self, p: Any) -> Optional[str]:
        if not p:
            return None
        path = str(p)
        if not os.path.isabs(path):
            path = str(self.project_root / path)
        return path if os.path.exists(path) else None

    def _build(self) -> None:
        for s in self.kb.symbols:
            refs = s.get("reference_images") or []
            paths = []
            for item in refs:
                p = item.get("local_path") or item.get("image_url") if isinstance(item, dict) else item
                rp = self._resolve(p)
                if rp:
                    paths.append(rp)
            if not paths:
                continue
            embs = self.clip.encode_images(paths)  # [n, 512] 已 L2 归一化
            self._ref_embs[str(s["symbol_id"])] = embs
            self.symbol_ids.append(str(s["symbol_id"]))

    def has_reference(self, symbol_id: str) -> bool:
        return symbol_id in self._ref_embs

    def frame_matrix(self, frame_paths: List[str]) -> Tuple[torch.Tensor, List[str]]:
        """返回 M=[frames, symbols] 的逐帧最大参考图相似度，以及参与比较的 symbol 顺序。"""
        if not frame_paths or not self.symbol_ids:
            return torch.zeros(0, 0), []
        frames = self.clip.encode_images(frame_paths)  # [f, 512]
        cols = []
        for sid in self.symbol_ids:
            cols.append((frames @ self._ref_embs[sid].T).max(dim=1).values)  # [f]
        return torch.stack(cols, dim=1), self.symbol_ids

    def evidence(self, matrix: torch.Tensor, symbol_ids: List[str], symbol_id: str) -> Dict[str, Any]:
        """候选的视觉身份证据：max / top-k 参考图相似度 + 多帧一致性。"""
        if matrix.numel() == 0 or symbol_id not in symbol_ids:
            return {"available": False, "max_ref_sim": None, "topk_ref_sim": None,
                    "frame_consistency": None, "frames_best_is_candidate": 0}
        col = matrix[:, symbol_ids.index(symbol_id)]  # [frames]
        sims, best = torch.sort(col, descending=True)
        topk = sims[:min(3, sims.numel())]
        argmax_all = matrix.argmax(dim=1)
        best_names = [symbol_ids[int(i)] for i in argmax_all]
        hit = sum(1 for n in best_names if n == symbol_id)
        return {
            "available": True,
            "max_ref_sim": float(sims[0]),
            "topk_ref_sim": float(topk.mean()),
            "frame_consistency": hit / matrix.shape[0],
            "frames_best_is_candidate": hit,
            "n_frames": int(matrix.shape[0]),
        }


# --------------------------------------------------------------------------- #
# 证据分层与规则初筛
# --------------------------------------------------------------------------- #
@dataclass
class CandidateEvidence:
    symbol_id: str
    canonical_name: str
    rank: int
    symbol: Dict[str, Any]
    text_identity: str            # strong / weak / none
    text_detail: str
    visual_identity: str          # strong / supporting / none / unavailable
    visual_detail: str
    hierarchy_relation: str       # none / parent_entity / same_category / similar_entity ...
    strong_identity: bool
    supporting: List[str] = field(default_factory=list)
    category_only: bool = False
    verification_required: bool = False
    trigger_reasons: List[str] = field(default_factory=list)
    scores: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol_id": self.symbol_id, "canonical_name": self.canonical_name,
            "rank": self.rank, "text_identity": self.text_identity,
            "text_detail": self.text_detail, "visual_identity": self.visual_identity,
            "visual_detail": self.visual_detail, "hierarchy_relation": self.hierarchy_relation,
            "strong_identity": self.strong_identity, "supporting": self.supporting,
            "verification_required": self.verification_required,
            "trigger_reasons": self.trigger_reasons, "scores": self.scores,
        }


class IdentityVerifierV2:
    """规则分层 + 规则初筛 + 可选 LLM 二次核验。"""

    def __init__(self, kb: Optional[SymbolKnowledgeBase] = None,
                 clip_encoder=None, config_path: Optional[str] = None,
                 llm_caller=None, model_manager=None, scope_policy="v2"):
        if scope_policy not in {"v2", "kb_scope_v3"}:
            raise ValueError("Unknown identity scope policy")
        self.scope_policy = scope_policy
        self.kb = kb or SymbolKnowledgeBase()
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        with self.config_path.open(encoding="utf-8") as f:
            self.config = json.load(f)
        self.v1_text = IdentityEvidenceGate(self.kb)
        if clip_encoder is None:
            from .clip_encoder import CLIPEncoder
            clip_encoder = CLIPEncoder()
        self.clip = clip_encoder
        self.visual = VisualIdentityIndex(self.kb, self.clip)
        self.llm_caller = llm_caller
        if self.llm_caller is None and model_manager is not None:
            self.llm_caller = model_manager.call_glm_api
        self.vis_cfg = self.config["visual_identity"]
        self.ver_cfg = self.config["verification"]

    # ---------------- 证据分层 ---------------- #
    def _unique_feature_terms(self, symbol: Dict[str, Any]) -> List[str]:
        """把 KB 的 visual_features 拆成可匹配的独特特征词。

        原字段多为 `A/B（“C”528米）|D` 形式的复合列表，v1 因包含括号而整体跳过，
        导致「画面出现候选专属地标」这类强证据被漏掉。这里拆开并去除数量词，
        仅保留长度 >= 3 的中文特征词用于精确子串匹配（不做模糊匹配）。
        """
        raw = str(symbol.get("visual_features", "") or "")
        out: List[str] = []
        for seg in raw.split("|"):
            parts = [re.sub(r"[（(][^）)]*[）)]", "", seg)]
            parts += re.findall(r"[（(]([^）)]*)[）)]", seg)
            for part in parts:
                part = part.replace("“", "").replace("”", "").replace('"', "").replace("'", "")
                for tok in re.split(r"[/、，,；;]|以及|及", part):
                    tok = re.sub(r"\d+(?:\.\d+)?\s*(?:米|公里|km|m)?", "", tok).strip()
                    norm = re.sub(r"[\s\W_]+", "", tok)
                    if len(norm) >= 3 and re.search(r"[\u4e00-\u9fff]", norm):
                        out.append(norm)
        return list(dict.fromkeys(out))

    def _conflicting_focus_entity(self, focus: str, symbol: Dict[str, Any]) -> bool:
        """画面主体是否被明确指认为另一个具体实体。

        与 v1 的启发式相同，但扩充了通用名词表：`摩天大楼 / 总部大楼 / 大厦`
        这类描述性名词不是具体实体，不能作为「主体另有其人」的证据。
        """
        subject = self.v1_text._focus_subject(focus)
        if not subject:
            return False
        for _, term in _terms(symbol):
            subject = subject.replace(term, "")
        if re.search(r"[“\"'].*?[”\"']", subject):
            return True
        generic = ("现代化|现代都市|现代|传统|中式|宏伟|一座|建筑群|摩天大楼|摩天|大楼|大厦|"
                   "高楼|总部|中央|周围|周边|车流|河流|人群|街道|景观|广场|天空|画面|外观|"
                   "前方|及其|以及")
        residual = re.sub(generic, "", subject)
        return bool(re.search(r"[\u4e00-\u9fff]{2,}(?:门|中心|馆|堂|园|楼|塔|院|城)", residual))

    def _text_channel(self, candidate: Dict[str, Any], symbol: Dict[str, Any],
                      scene_description: str) -> Tuple[str, str]:
        """Text Identity Channel：canonical / alias / OCR 型专属文字 / KB 独特特征。"""
        focus = _focus_text(scene_description)
        text_ev = self.v1_text.assess_candidate(candidate, scene_description)
        canonical, alias = text_ev.identity_name_match, text_ev.identity_alias_match
        attrs = list(text_ev.unique_attribute_matches)

        # 纯 ASCII 缩写（如 CBD）在中文句子里出现即为完整实体，
        # 修复「北京CBD现代都市景观」被 v1 判成「更长实体的前缀」的问题。
        for kind, term in _terms(symbol):
            if re.fullmatch(r"[A-Za-z0-9]{2,}", str(term).strip()) and term in focus:
                canonical |= kind == "canonical"
                alias |= kind == "alias"

        for tok in self._unique_feature_terms(symbol):
            # 独特特征允许出现在【文化视觉元素】列表中：该列表是模型从关键帧抽取的
            # 专属地标/标识（如「中国尊」之于 CBD），精确命中即可作为身份线索。
            if tok in str(scene_description or ""):
                attrs.append(tok)
        attrs = list(dict.fromkeys(attrs))

        if canonical or alias or attrs:
            return "strong", (f"canonical={canonical}; alias={alias}; "
                              f"unique_feature={attrs}")
        if text_ev.weak_name_mentions:
            return "weak", f"仅上下文提及:{text_ev.weak_name_mentions}"
        return "none", "场景描述未出现候选名称/别名/独特特征"

    def build_candidate(self, candidate: Dict[str, Any], rank: int, scene_description: str,
                        matrix: torch.Tensor, symbol_ids: List[str]) -> CandidateEvidence:
        from ..pipeline.scene_evidence import subject_evidence_text
        scene_description = subject_evidence_text(scene_description)
        sid = str(candidate.get("symbol_id", ""))
        symbol = self.kb.get(sid) or candidate.get("raw") or {}
        # --- Text Identity Channel（复用 v1 的完整实体匹配，但不再作为唯一判据） ---
        text_identity, text_detail = self._text_channel(candidate, symbol, scene_description)

        # 父/子实体关系：候选名出现在另一个被明确指认的实体内部，或反之
        hierarchy = self._hierarchy_relation(symbol, scene_description)
        if hierarchy == "none" and self._conflicting_focus_entity(
                _focus_text(scene_description), symbol):
            # 画面主体被明确指认为另一个具体实体（如某个门/殿/楼），
            # 候选只能是其父级/同景区/相似实体，不能据此确认 exact identity
            hierarchy = "parent_entity"

        # --- Visual Identity Channel --- #
        vis = self.visual.evidence(matrix, symbol_ids, sid)
        if not vis["available"]:
            visual_identity, visual_detail = "unavailable", "KB 无真实参考图"
        else:
            strong_v = (vis["max_ref_sim"] >= self.vis_cfg["max_ref_sim_strong"]
                        and vis["topk_ref_sim"] >= self.vis_cfg["topk_ref_sim_strong"]
                        and vis["frame_consistency"] >= self.vis_cfg["frame_consistency_strong"])
            support_v = (vis["max_ref_sim"] >= self.vis_cfg["max_ref_sim_supporting"]
                         or vis["frame_consistency"] >= self.vis_cfg["frame_consistency_supporting"])
            visual_identity = "strong" if strong_v else ("supporting" if support_v else "none")
            visual_detail = (f"max_ref_sim={vis['max_ref_sim']:.3f}; "
                             f"top3_ref_sim={vis['topk_ref_sim']:.3f}; "
                             f"frame_consistency={vis['frame_consistency']:.2f} "
                             f"({vis['frames_best_is_candidate']}/{vis['n_frames']} 帧最优)")

        strong_identity = (text_identity == "strong") or (visual_identity == "strong")
        # 父/子实体关系存在时，即使命中名称也不算 exact identity
        if hierarchy in ("parent_entity", "child_entity"):
            strong_identity = False

        supporting = []
        if text_identity == "weak":
            supporting.append("text_context_mention")
        if visual_identity == "supporting":
            supporting.append("visual_reference_match")

        ev = CandidateEvidence(
            symbol_id=sid, canonical_name=str(symbol.get("canonical_name", candidate.get("canonical_name", ""))),
            rank=rank, symbol=symbol, text_identity=text_identity, text_detail=text_detail,
            visual_identity=visual_identity, visual_detail=visual_detail,
            hierarchy_relation=hierarchy, strong_identity=strong_identity,
            supporting=supporting,
            category_only=(hierarchy != "none"),
            scores={"text_score": candidate.get("text_score"), "image_score": candidate.get("image_score"),
                    "fusion_score": candidate.get("fusion_score")},
        )
        return ev

    def _hierarchy_relation(self, symbol: Dict[str, Any], scene_description: str) -> str:
        """用通用规则识别父子/同类关系，不做任何具体样本的硬编码。"""
        focus = _focus_text(scene_description)
        terms = [str(symbol.get("canonical_name", ""))] + \
                [t for t in str(symbol.get("aliases", "")).split("|") if t]
        # 候选名作为另一个更长实体的组成部分（如「故宫博物院的神武门」中的 故宫）
        for term in terms:
            if not term or term not in focus:
                continue
            for m in re.finditer(re.escape(term), focus):
                tail = focus[m.end():m.end() + 6]
                if re.match(r"[的了之内的位于属]", tail) and re.search(r"[\u4e00-\u9fff]{2,}(门|殿|楼|阁|塔|堂|馆|园|宫)$", tail):
                    return "parent_entity"
                if re.match(r"[\u4e00-\u9fff]{2,}$", tail) and re.match(r"^[\u4e00-\u9fff]{2,}(门|殿|楼|阁|塔)", tail):
                    return "parent_entity"
        # KB 声明的 related_symbols 关系 → 同景区/同类
        related = str(symbol.get("related_symbols", "") or "")
        for other in self.kb.symbols:
            name = str(other.get("canonical_name", ""))
            if name and name != symbol.get("canonical_name") and name in related and name in focus:
                return "same_scenic_area"
        return "none"

    # ---------------- 规则初筛 ---------------- #
    def screen(self, evidence: List[CandidateEvidence], mode: str,
               text_top1: Optional[str], image_top1: Optional[str]) -> None:
        """为每个候选打 verification_required 标记（只做规则判断，不调用 LLM）。

        关键设计：A 类强身份证据（canonical/alias/独特属性/视觉强匹配）且无父子实体冲突时
        **直接判定 accept**，不送入 Verifier——否则会把明确的 Known 样本交给保守的
        二次模型，重新引入 v1 式的过拒。
        """
        if not evidence:
            return
        top1 = evidence[0]
        margin = None
        if len(evidence) > 1:
            s1 = top1.scores.get("fusion_score")
            s2 = evidence[1].scores.get("fusion_score")
            if isinstance(s1, (int, float)) and isinstance(s2, (int, float)):
                margin = abs(s1 - s2)

        for ev in evidence:
            # A 类强证据 + 无层级冲突 → 直接 accept，无需核验
            if ev.strong_identity and ev.hierarchy_relation == "none":
                ev.trigger_reasons = []
                ev.verification_required = False
                continue

            reasons = []
            if ev.hierarchy_relation in ("parent_entity", "child_entity", "same_scenic_area"):
                reasons.append("hierarchy_relation_with_subject")
            if ev.text_identity == "weak" and ev.visual_identity in ("strong", "supporting"):
                reasons.append("text_weak_visual_support")
            if ev.text_identity == "none" and ev.visual_identity in ("strong", "supporting"):
                reasons.append("text_missing_visual_present")
            if ev.text_identity == "strong" and not ev.strong_identity:
                # 名称命中但被层级规则降级（父子实体），需要核验是否为同一身份
                reasons.append("name_hit_but_hierarchy_conflict")
            if margin is not None and margin < self.ver_cfg["score_margin_threshold"] and ev.rank == 0:
                reasons.append("top1_top2_close")
            if text_top1 and image_top1 and text_top1 != image_top1 and ev.rank == 0:
                reasons.append("text_image_disagreement")
            if ev.rank == 0 and not ev.strong_identity and \
                    isinstance(ev.scores.get("fusion_score"), (int, float)) and \
                    ev.scores["fusion_score"] >= self.ver_cfg["high_fusion_threshold"]:
                reasons.append("high_score_without_identity")
            ev.trigger_reasons = reasons
            ev.verification_required = bool(reasons)

    # ---------------- LLM 二次核验 ---------------- #
    def verify_with_llm(self, ev: CandidateEvidence, scene_description: str,
                        frame_paths: List[str]) -> Dict[str, Any]:
        if self.llm_caller is None:
            return {"identity_status": STATUS_INSUFFICIENT, "reason": "verifier_unavailable",
                    "confidence": 0.0, "text_identity_evidence": "none",
                    "visual_identity_evidence": "none", "hierarchy_relation": ev.hierarchy_relation}

        import base64
        content: List[Dict[str, Any]] = []
        for p in frame_paths[:self.ver_cfg["max_images"]]:
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        content.append({"type": "text", "text": self._verifier_user_prompt(ev, scene_description)})
        system_prompt = VERIFIER_SYSTEM_PROMPT
        if self.scope_policy == "kb_scope_v3":
            system_prompt += "\n身份粒度补充：以知识库规范名、别名、类型、典型场景共同定义候选范围。复合文化场所不要求整片区域同时入镜；若关键帧中的主体确为KB明确覆盖的表现形式，可接受。典型场景仅界定范围，不能代替视觉身份证据。不能因背景出现父实体、仅同景区或存在通用外观就接受；若主体是KB范围外的另一个具名实体，仍须拒绝。先核对范围，再核对可见证据。背景只作辅助，禁止单独作为主体身份依据。"
        messages = [{"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}]
        raw = self.llm_caller(messages, temperature=self.ver_cfg["temperature"])
        return self._parse_verifier_output(raw, ev)

    def _verifier_user_prompt(self, ev: CandidateEvidence, scene_description: str) -> str:
        s = ev.symbol
        return f"""【视频关键帧】已提供 {self.ver_cfg['max_images']} 张（按时间均匀采样）。

【Pass-1 场景描述】
{str(scene_description)[:1500]}

【待核验候选】
- 规范名：{s.get('canonical_name','')}
- 别名：{s.get('aliases','')}
- 文化维度：{s.get('dimension_code','')}
- 类型：{s.get('symbol_type','')}
- 典型场景：{s.get('typical_scene','') if self.scope_policy == 'kb_scope_v3' else '未启用范围核验'}
- 地域：{s.get('region','')}
- 视觉特征：{s.get('visual_features','')}
- 文化描述：{str(s.get('cultural_description',''))[:300]}
- 参考图：KB 中该候选存在 {len(s.get('reference_images') or [])} 张参考图

【检索分数】text={ev.scores.get('text_score')} image={ev.scores.get('image_score')} fusion={ev.scores.get('fusion_score')}

【规则层证据摘要】
- 文本身份证据：{ev.text_identity}（{ev.text_detail}）
- 视觉身份证据：{ev.visual_identity}（{ev.visual_detail}）
- 层级关系：{ev.hierarchy_relation}

请判断：视频证据是否足以证明视频中的具体文化实体就是上述候选本身（exact identity）。特别注意：若画面/描述只能证明它位于、属于或相似于该候选所属的建筑群/景区/类别，则必须输出 reject_related_but_not_exact。"""

    @staticmethod
    def _parse_verifier_output(raw: str, ev: CandidateEvidence) -> Dict[str, Any]:
        status = STATUS_INSUFFICIENT
        reason, text_ev, vis_ev, hier, conf = "", "none", "none", ev.hierarchy_relation, 0.0
        try:
            start, end = raw.find("{"), raw.rfind("}") + 1
            data = json.loads(raw[start:end]) if start >= 0 and end > 0 else {}
            status = str(data.get("identity_status", "")).strip()
            if status not in (STATUS_ACCEPT, STATUS_RELATED, STATUS_INSUFFICIENT):
                status = STATUS_INSUFFICIENT
            reason = str(data.get("reason", ""))[:300]
            text_ev = str(data.get("text_identity_evidence", "none"))[:200]
            vis_ev = str(data.get("visual_identity_evidence", "none"))[:200]
            hier = str(data.get("hierarchy_relation", hier))[:60]
            try:
                conf = float(data.get("confidence", 0.0))
            except (TypeError, ValueError):
                conf = 0.0
        except Exception as exc:  # noqa: BLE001
            reason = f"parse_error: {exc}"
        return {"identity_status": status, "reason": reason, "confidence": conf,
                "text_identity_evidence": text_ev, "visual_identity_evidence": vis_ev,
                "hierarchy_relation": hier}

    # ---------------- 单视频决策 ---------------- #
    def _rule_status(self, ev: CandidateEvidence) -> Dict[str, Any]:
        """规则层给出的身份判定（不调用 LLM）。"""
        if ev.strong_identity and ev.hierarchy_relation == "none":
            status, reason = STATUS_ACCEPT, "strong_identity_evidence"
        elif ev.hierarchy_relation in ("parent_entity", "child_entity", "same_scenic_area"):
            status, reason = STATUS_RELATED, f"hierarchy:{ev.hierarchy_relation}"
        elif ev.visual_identity == "supporting" or ev.text_identity == "weak":
            status, reason = STATUS_INSUFFICIENT, "supporting_evidence_only"
        else:
            status, reason = STATUS_INSUFFICIENT, "no_identity_evidence"
        return {"identity_status": status, "reason": reason,
                "confidence": 1.0 if status == STATUS_ACCEPT else 0.0,
                "text_identity_evidence": ev.text_detail,
                "visual_identity_evidence": ev.visual_detail,
                "hierarchy_relation": ev.hierarchy_relation}

    def decide(self, video_id: str, video_path: str, scene_description: str,
               candidates: List[Dict[str, Any]], pred_symbol: str = "",
               text_top1: Optional[str] = None, image_top1: Optional[str] = None,
               enable_llm: bool = True) -> Dict[str, Any]:
        """对一个视频给出唯一最终判定。

        只对模型最终选择的候选做身份核验；核验层是「减法层」，
        不会用其它候选替换模型的选择，因此不会引入新的接受行为。
        """
        frame_paths = extract_keyframes(video_path, video_id, self.ver_cfg["num_frames"])
        matrix, symbol_ids = self.visual.frame_matrix(frame_paths)

        top = candidates[:self.ver_cfg["max_candidates"]]
        ordered: List[Dict[str, Any]] = []
        if pred_symbol:
            for c in candidates:
                if str(c.get("canonical_name", "")) == str(pred_symbol):
                    ordered.append(c)
        if pred_symbol and not ordered:
            return {"video_id": video_id, "final_symbol": "", "final_status": STATUS_INSUFFICIENT,
                    "final_reason": "predicted_symbol_not_in_candidates", "verification_required": False,
                    "candidates_verified": [], "decisions": [], "n_llm_calls": 0}
        ordered += [c for c in top if c not in ordered]
        ordered = ordered[:self.ver_cfg["max_candidates"]]

        evidence = [self.build_candidate(c, i, scene_description, matrix, symbol_ids)
                    for i, c in enumerate(ordered)]
        self.screen(evidence, "multimodal_controlled", text_top1, image_top1)

        decisions: List[Dict[str, Any]] = []
        if not evidence:
            return {"video_id": video_id, "final_symbol": "", "final_status": STATUS_INSUFFICIENT,
                    "final_reason": "no_candidates", "verification_required": False,
                    "candidates_verified": [], "decisions": [], "n_llm_calls": 0}

        primary = evidence[0]
        if primary.verification_required and enable_llm:
            res = self.verify_with_llm(primary, scene_description, frame_paths)
            source = "llm_verifier"
        else:
            res = self._rule_status(primary)
            source = "rule_screen"
        decisions.append(dict(res, **primary.to_dict(), source=source,
                              verifier_hierarchy_relation=res.get("hierarchy_relation")))

        for ev in evidence[1:]:
            decisions.append(dict(ev.to_dict(), source="rule_screen_only", **self._rule_status(ev)))

        accepted = res["identity_status"] == STATUS_ACCEPT
        return {
            "video_id": video_id,
            "final_symbol": primary.canonical_name if accepted else "",
            "final_status": res["identity_status"],
            "final_reason": res.get("reason", ""),
            "verification_required": primary.verification_required,
            "candidates_verified": [e.to_dict() for e in evidence],
            "decisions": decisions,
            "n_llm_calls": 1 if source == "llm_verifier" else 0,
            "visual_available": bool(symbol_ids) and primary.symbol_id in symbol_ids,
        }
