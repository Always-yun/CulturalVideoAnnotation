"""Build an audit table for Known / Easy Unknown / Hard Unknown samples.

This script is deliberately offline: it only reads the saved final test
results, the versioned GT split, and the saved validation signals.  It never
invokes the VLM, CLIP, or a retriever.  Unknown type is an audit annotation
based on the target named in the GT notes and on KB coverage, never on the
model prediction.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple


ROOT = Path(__file__).resolve().parents[2]
GT_PATH = ROOT / "experiments/innovation2/data/eval/cultural_ablation_gt_v2.jsonl"
RESULTS_PATH = ROOT / "experiments/innovation2/runs/cultural_ablation/gate_on_final/results.json"
VAL_SIGNALS_PATH = ROOT / "experiments/innovation2/cache/rejection_val_signals.json"
OUT_PATH = ROOT / "experiments/innovation2/results/cultural_rag/unknown_analysis/cultural_unknown_analysis.csv"


# These are dataset audit labels.  They describe the target-to-KB relation and
# are intentionally independent of the saved system output.
UNKNOWN_AUDIT: Dict[str, Dict[str, str]] = {
    "神武门": {
        "target": "神武门",
        "unknown_type": "hard_unknown",
        "category_evidence": "古建筑/故宫建筑群（ANCIENT）",
        "identity_evidence": "目标无独立KB条目；故宫为父实体，不能证明神武门条目身份",
        "notes": "细粒度缺口：KB故宫条目的visual_features提及神武门，但规范名/别名均不是神武门。",
    },
    "中关村国际创新中心": {
        "target": "中关村国际创新中心",
        "unknown_type": "hard_unknown",
        "category_evidence": "科技园区/中关村语义族（TECH）",
        "identity_evidence": "目标无独立KB条目；中关村/中关村科学城为同地域与同功能近邻，不能证明具体建筑身份",
        "notes": "名称、地域、功能均与KB近邻高度相似。",
    },
    "人民大会堂1": {
        "target": "人民大会堂",
        "unknown_type": "hard_unknown",
        "category_evidence": "国家公共建筑/红色文化近邻（RED）",
        "identity_evidence": "目标无独立KB条目；同维度和邻近地标不是人民大会堂身份依据",
        "notes": "测试集Hard Unknown：与天安门广场、国家博物馆等现有KB候选语义相邻。",
    },
    "人民大会堂": {
        "target": "人民大会堂",
        "unknown_type": "hard_unknown",
        "category_evidence": "国家公共建筑/红色文化近邻（RED）",
        "identity_evidence": "目标无独立KB条目；同维度和邻近地标不是人民大会堂身份依据",
        "notes": "验证集Hard Unknown。",
    },
    "中关村展示中心": {
        "target": "中关村展示中心",
        "unknown_type": "hard_unknown",
        "category_evidence": "科技园区/中关村语义族（TECH）",
        "identity_evidence": "目标无独立KB条目；中关村类候选不足以确认具体展示中心",
        "notes": "验证集Hard Unknown。",
    },
    "糖葫芦": {
        "target": "冰糖葫芦",
        "unknown_type": "easy_unknown",
        "category_evidence": "民俗小吃（FOLK）",
        "identity_evidence": "无独立KB条目；KB中的北京烤鸭仅为宽泛饮食类别近邻，名称和外观均不相同",
        "notes": "验证集Easy Unknown：只有宽类别关联，没有同地标、同名称或近似外观的具体候选。",
    },
}


FIELDNAMES = [
    "video_id", "split", "mode", "ground_truth_symbol", "kb_covered",
    "unknown_type", "top1_candidate", "top1_score", "top2_candidate",
    "top2_score", "score_margin", "relative_margin", "text_score",
    "image_score", "fusion_score", "final_prediction", "rejected",
    "error_type", "category_evidence", "identity_evidence", "notes", "source",
]


def load_gt() -> Dict[str, Dict[str, Any]]:
    items = {}
    with GT_PATH.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            items[row["video_id"]] = row
    return items


def top_two(scores: Dict[str, Any], candidates: Iterable[Dict[str, Any]]) -> Tuple[str, Any, str, Any, Any]:
    names = {c.get("symbol_id"): c.get("canonical_name", "") for c in candidates}
    ranked = sorted(((str(k), float(v)) for k, v in (scores or {}).items()), key=lambda x: x[1], reverse=True)
    if not ranked:
        return "", "", "", "", ""
    first = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    return (
        names.get(first[0], first[0]), round(first[1], 4),
        names.get(second[0], second[0]) if second else "",
        round(second[1], 4) if second else "",
        round(first[1] - second[1], 4) if second else "",
    )


def audit_for(gt: Dict[str, Any]) -> Dict[str, str]:
    if gt.get("kb_coverage") == "hit":
        return {
            "target": " / ".join(gt.get("gt_symbols", [])),
            "unknown_type": "known",
            "category_evidence": f"GT维度：{gt.get('gt_dimension_code', '')}",
            "identity_evidence": "GT指定的KB symbol_id：" + ";".join(gt.get("gt_symbol_ids", [])),
            "notes": gt.get("notes", ""),
        }
    return UNKNOWN_AUDIT.get(gt["video_id"], {
        "target": "unknown_symbol",
        "unknown_type": "unreviewed_unknown",
        "category_evidence": f"GT维度：{gt.get('gt_dimension_code', '')}",
        "identity_evidence": "待人工审计",
        "notes": gt.get("notes", ""),
    })


def test_rows(gt_by_id: Dict[str, Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    records = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))["records"]
    for r in records:
        gt = gt_by_id[r["video_id"]]
        audit = audit_for(gt)
        top1, top1_score, top2, top2_score, margin = top_two(
            r.get("fusion_scores") or r.get("text_scores"), r.get("topk_candidates", []))
        # Preserve individual modalities separately.  Values are the Top-1
        # values in the saved artefact; text scale differs for text-only mode.
        _, text_score, _, _, _ = top_two(r.get("text_scores", {}), r.get("topk_candidates", []))
        _, image_score, _, _, _ = top_two(r.get("image_scores", {}), r.get("topk_candidates", []))
        _, fusion_score, _, _, _ = top_two(r.get("fusion_scores", {}), r.get("topk_candidates", []))
        rejected = bool(r.get("unknown_symbol", False))
        if gt.get("kb_coverage") == "gap":
            error_type = "correct_rejection" if rejected else "forced_match_or_identity_hallucination"
        elif rejected:
            error_type = "known_false_reject"
        elif r.get("hallucination"):
            error_type = "known_prediction_outside_kb"
        else:
            error_type = "known_or_unchecked_prediction"
        yield {
            "video_id": r["video_id"], "split": r.get("split", "test"), "mode": r.get("mode", ""),
            "ground_truth_symbol": audit["target"], "kb_covered": gt.get("kb_coverage", ""),
            "unknown_type": audit["unknown_type"], "top1_candidate": top1,
            "top1_score": top1_score, "top2_candidate": top2, "top2_score": top2_score,
            "score_margin": margin, "relative_margin": (r.get("gate_signals") or {}).get("margin_rel", ""),
            "text_score": text_score, "image_score": image_score, "fusion_score": fusion_score,
            "final_prediction": r.get("pred_symbol", ""), "rejected": rejected,
            "error_type": error_type, "category_evidence": audit["category_evidence"],
            "identity_evidence": audit["identity_evidence"], "notes": audit["notes"],
            "source": "gate_on_final/results.json",
        }


def validation_rows(gt_by_id: Dict[str, Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    """Add existing validation signals without inventing candidates or predictions."""
    samples = json.loads(VAL_SIGNALS_PATH.read_text(encoding="utf-8"))["samples"]
    for s in samples:
        gt = gt_by_id[s["video_id"]]
        audit = audit_for(gt)
        text = s["text"]
        image = s["image"]
        fusion = s["multimodal"]
        yield {
            "video_id": s["video_id"], "split": "val", "mode": "multimodal_validation_signal",
            "ground_truth_symbol": audit["target"], "kb_covered": gt.get("kb_coverage", ""),
            "unknown_type": audit["unknown_type"], "top1_candidate": "",
            "top1_score": fusion[0], "top2_candidate": "", "top2_score": fusion[1],
            "score_margin": round(fusion[0] - fusion[1], 4),
            "relative_margin": round((fusion[0] - fusion[1]) / fusion[0], 4) if fusion[0] else 0.0,
            "text_score": text[0], "image_score": image[0], "fusion_score": fusion[0],
            "final_prediction": "", "rejected": "", "error_type": "not_run_in_final_test",
            "category_evidence": audit["category_evidence"], "identity_evidence": audit["identity_evidence"],
            "notes": audit["notes"], "source": "experiments/innovation2/cache/rejection_val_signals.json",
        }


def main() -> None:
    gt_by_id = load_gt()
    rows = list(test_rows(gt_by_id)) + list(validation_rows(gt_by_id))
    with OUT_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
