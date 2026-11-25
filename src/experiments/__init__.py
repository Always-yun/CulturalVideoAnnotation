"""创新点2 消融实验模块（检索/标注指标 + 5模式运行器）"""

from .ablation_metrics import (
    load_gt,
    build_kb_vocab,
    compute_retrieval_metrics,
    compute_annotation_metrics,
    compute_mode_summary,
    is_hallucination,
    hit_gt_symbol,
    dimension_hit,
)
from .ablation_runner import CulturalAblationExperiment, ALL_MODES

__all__ = [
    "load_gt", "build_kb_vocab",
    "compute_retrieval_metrics", "compute_annotation_metrics",
    "compute_mode_summary", "is_hallucination", "hit_gt_symbol", "dimension_hit",
    "CulturalAblationExperiment", "ALL_MODES",
]
