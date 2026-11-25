"""
拒识门控 RejectionGate（创新点2优化：知识库覆盖缺口样本拒识）

动机（2026-10-15 旧实验根因分析，experiments/innovation2/runs/cultural_ablation/20261015_143003）：
- 检索分数/分差信号从未传递给标注模型：3 个 KB 覆盖缺口样本（GT=unknown_symbol）
  的 Top1-Top2 融合分差仅 0.0006~0.002，但候选注入 Prompt 时不带置信度信息；
- 受控模式"仅当画面证据确认为候选之外时输出 unknown_symbol"逃生口过宽，
  模型输出候选外名称（"石碑、石亭"）绕过闭集；
- 候选无条件注入：检索分数再低也照常注入 Top-K，模型顺着候选强行匹配，
  unknown 拒识率全模式 = 0。

三信号：
  S1 检索分数   top1 主分数（text 家族 = text_score 原始加权命中分；
                 clip 家族 = fusion_score，image 模式 alpha=0 时即图像分）
  S2 分差       margin_rel = (top1 - top2) / max(top1, eps)，相对分差抗量纲
  S3 视觉证据   KB 词表扫描命中关键词数 n_keywords；
                 Pass-1 场景描述负信号（明确输出"无明确文化符号"）

决策（阈值全部来自 experiments/innovation2/data/eval/rejection_thresholds.json，由验证集网格搜索产出，
     禁止在代码中硬编码业务阈值）：
  insufficient  top1 < score_thr 或（require_keywords 且 n_keywords==0）
                或场景描述负信号 → 候选不可信，Prompt 强制输出 unknown_symbol
  uncertain     分数达标但 margin_rel < margin_thr → 注入区分度警告
  confident     正常注入
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 配置文件默认路径（由 scripts/innovation2/tune_rejection_thresholds.py 产出）
DEFAULT_THRESHOLDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'experiments/innovation2/data/eval/rejection_thresholds.json')

# Pass-1 场景描述的负信号短语（与 cultural_rag.SCENE_DESCRIBE_PROMPT 约定一致）
SCENE_NEGATIVE_PHRASE = "无明确文化符号"

# 门控三档
LEVEL_CONFIDENT = "confident"
LEVEL_UNCERTAIN = "uncertain"
LEVEL_INSUFFICIENT = "insufficient"


@dataclass
class GateDecision:
    """单次门控决策：档位 + 信号快照 + 可解释原因"""
    level: str
    signals: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"level": self.level, "signals": self.signals, "reason": self.reason}


class RejectionGate:
    """基于检索分数 / Top1-Top2 分差 / 视觉证据充分性的三信号拒识门控

    Args:
        thresholds_path: 阈值配置 JSON 路径（验证集网格搜索产出）；
            None 时用 DEFAULT_THRESHOLDS_PATH，文件不存在则抛错（避免静默硬编码）。
    """

    def __init__(self, thresholds_path: Optional[str] = None):
        self.thresholds_path = thresholds_path or DEFAULT_THRESHOLDS_PATH
        if not os.path.exists(self.thresholds_path):
            raise FileNotFoundError(
                f"拒识阈值配置不存在: {self.thresholds_path}，"
                "请先运行 scripts/innovation2/tune_rejection_thresholds.py 在验证集上搜索阈值")
        with open(self.thresholds_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.thresholds: Dict[str, Dict[str, Any]] = self.config["thresholds"]

    # ------------------------------------------------------------------ #
    # 阈值族选择：text 家族用原始文本分；image / multimodal（含受控）用融合分
    # ------------------------------------------------------------------ #
    @staticmethod
    def family_for(mode: str) -> str:
        if mode == "text":
            return "text"
        if mode in ("image", "multimodal", "multimodal_controlled"):
            return mode if mode in ("image", "multimodal") else "multimodal"
        # 兜底：按检索器名推断由调用方显式传 mode
        return "multimodal"

    def thresholds_for(self, mode: str) -> Dict[str, Any]:
        fam = self.family_for(mode)
        if fam not in self.thresholds:
            raise KeyError(f"阈值配置缺少模式族: {fam}（{sorted(self.thresholds)}）")
        return self.thresholds[fam]

    # ------------------------------------------------------------------ #
    # 主决策入口
    # ------------------------------------------------------------------ #
    def decide(self, candidates: List[Any], keywords: Optional[List[str]] = None,
               scene_description: str = "", mode: str = "multimodal") -> GateDecision:
        """
        Args:
            candidates: CulturalCandidate 列表（retrieve 输出）
            keywords: extract_cultural_query 命中的 KB 词表关键词
            scene_description: Pass-1 场景描述文本
            mode: 实验模式名（text/image/multimodal/multimodal_controlled）
        """
        thr = self.thresholds_for(mode)
        n_kw = len(keywords or [])
        scene_neg = SCENE_NEGATIVE_PHRASE in str(scene_description or "")

        if not candidates:
            return GateDecision(LEVEL_INSUFFICIENT,
                                {"n_keywords": n_kw, "scene_negative": scene_neg,
                                 "top1_score": None, "margin_rel": None},
                                "检索无任何候选")

        top1, top2 = self._top_scores(candidates, thr.get("signal", "fusion"))
        return self.decide_from_signals(top1, top2, n_kw, scene_neg, mode)

    def decide_from_signals(self, top1: float, top2: float,
                            n_keywords: int, scene_negative: bool,
                            mode: str) -> GateDecision:
        """基于原始三信号决策（与 decide 同逻辑；供阈值搜索脚本精确复用）"""
        thr = self.thresholds_for(mode)
        margin_rel = (top1 - top2) / top1 if top1 > 1e-6 else 0.0
        signals = {
            "mode": mode, "signal": thr.get("signal", "fusion"),
            "top1_score": round(top1, 4), "top2_score": round(top2, 4),
            "margin_rel": round(margin_rel, 4),
            "n_keywords": n_keywords, "scene_negative": scene_negative,
            "score_thr": thr["score_thr"], "margin_thr": thr["margin_thr"],
        }

        # S1 检索分数门控
        if top1 < thr["score_thr"]:
            return GateDecision(
                LEVEL_INSUFFICIENT, signals,
                f"Top1检索分 {top1:.3f} 低于门限 {thr['score_thr']}")
        # S3 视觉证据：无 KB 词表命中 / 场景描述明确无文化符号
        if thr.get("require_keywords", True) and n_keywords == 0:
            return GateDecision(
                LEVEL_INSUFFICIENT, signals,
                "视觉描述无任何知识库词表命中（n_keywords=0）")
        if scene_negative:
            return GateDecision(
                LEVEL_INSUFFICIENT, signals,
                "Pass-1场景描述明确输出'无明确文化符号'")
        # S2 分差门控：分数达标但候选区分度不足
        if margin_rel < thr["margin_thr"]:
            return GateDecision(
                LEVEL_UNCERTAIN, signals,
                f"Top1-Top2相对分差 {margin_rel:.4f} 低于门限 {thr['margin_thr']}")
        return GateDecision(LEVEL_CONFIDENT, signals,
                            "检索分数/分差/视觉证据三信号均达标")

    @staticmethod
    def _top_scores(candidates: List[Any], signal: str) -> tuple:
        """取前两高的主分数（不假设候选已按该分数排序）"""
        def score_of(c):
            for f in (signal, "fusion_score", "score", "text_score"):
                v = getattr(c, f, None)
                if v is None and isinstance(c, dict):
                    v = c.get(f, None)
                if v is not None:
                    return float(v)
            return 0.0
        scores = sorted((score_of(c) for c in candidates), reverse=True)
        top1 = scores[0] if scores else 0.0
        top2 = scores[1] if len(scores) > 1 else 0.0
        return top1, top2
