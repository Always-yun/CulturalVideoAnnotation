"""
创新点2 正式实验（31 条人工核验文化视频）统计与论文产物生成

输入：
  experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl          — 冻结 GT（含 sample_type）
  experiments/innovation2/runs/cultural_ablation/final30_exp1/results.json — 实验一：5 模式 + Existing Gate
  experiments/innovation2/runs/cultural_ablation/final30_exp2_identity/results.json
                                                        — 实验二：+ Identity Evidence Gate

输出（experiments/innovation2/results/cultural_rag/final30/）：
  experiment1_results.csv / experiment1_main_table.csv
  experiment2_results.csv / experiment2_main_table.csv
  final30_predictions.csv / hard_unknown_case_analysis.csv
  retrieval_metrics_plot.csv / hallucination_comparison.csv
  gate_comparison.csv / score_distribution.csv
  innovation2_final_experiment_report.md

指标定义（不依赖模型自评，全部由 GT 与落盘记录确定性计算）：
  Known 样本（gt_symbol_ids 非空）
    Recall@1 / Recall@5 / MRR   — 检索候选层面
    Symbol Accuracy             — 最终符号命中 GT 规范名/别名（未拒识前提下）
    Dimension Accuracy          — 最终维度码命中 GT 维度码
  Unknown 样本（gt_symbol_ids 为空）
    Rejection Rate              — 最终输出 unknown_symbol 的比例
  全部样本
    Hallucination Rate          — 输出具体符号但不含任何 KB 词表项（编造符号）
  False Rejection Rate          — Known 样本被拒识的比例
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.experiments.ablation_metrics import (
    build_kb_vocab, hit_gt_symbol, is_hallucination, dimension_hit,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GT_PATH = os.path.join(PROJECT_ROOT, "experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl")
EXP1_PATHS = [
    os.path.join(PROJECT_ROOT, "experiments/innovation2/runs/cultural_ablation/final30_exp1/results.json"),
    # 修复「真实参考图参与图像编码」后重跑的 Image/Multimodal/Controlled 记录，优先级更高
    os.path.join(PROJECT_ROOT,
                 "experiments/innovation2/runs/cultural_ablation/final30_exp1_imgfix/results.json"),
]
EXP2_PATHS = [
    os.path.join(PROJECT_ROOT,
                 "experiments/innovation2/runs/cultural_ablation/final30_exp2_identity/results.json"),
    os.path.join(PROJECT_ROOT,
                 "experiments/innovation2/runs/cultural_ablation/final30_exp2_imgfix/results.json"),
]
OUT_DIR = os.path.join(PROJECT_ROOT, "experiments/innovation2/results/cultural_rag/final30")

MODES = ["free", "text", "image", "multimodal", "multimodal_controlled"]
MODE_LABEL = {"free": "Free", "text": "Text", "image": "Image",
              "multimodal": "Multimodal", "multimodal_controlled": "Multimodal Controlled"}
GATE_BASELINE = "existing_gate"
GATE_IDENTITY = "identity_gate"
GATE_LABEL = {GATE_BASELINE: "Existing Gate", GATE_IDENTITY: "+ Identity Evidence Gate"}
DIM_LABEL = {"ANCIENT": "ANCIENT", "RED": "RED", "FOLK": "FOLK",
             "TECH": "TECH", "MODERN": "MODERN"}


# ---------------------------------------------------------------------- #
# 数据装载
# ---------------------------------------------------------------------- #
def load_jsonl(path: str) -> List[Dict[str, Any]]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def load_results(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("records", [])


def load_merged(paths: List[str]) -> List[Dict[str, Any]]:
    """按 (video_id, mode) 合并多次运行记录；后面的路径优先级更高"""
    merged: Dict[tuple, Dict[str, Any]] = {}
    for p in paths:
        for rec in load_results(p):
            merged[(rec.get("video_id"), rec.get("mode"))] = rec
    return list(merged.values())


def reference_image_map(kb: SymbolKnowledgeBase) -> Dict[str, int]:
    """symbol_id → 可用本地参考图数量（用于 image_evidence_status 判定）"""
    def usable(p: Any) -> bool:
        if not p:
            return False
        path = str(p)
        if not os.path.isabs(path):
            path = os.path.join(PROJECT_ROOT, path)
        return os.path.exists(path)

    out = {}
    for s in kb.symbols:
        refs = s.get("reference_images") or []
        n = 0
        if isinstance(refs, list):
            for item in refs:
                if isinstance(item, dict):
                    # 以「本地参考图文件是否可用」为唯一判据：这些图正是检索时实际编码的图像
                    if usable(item.get("local_path")) or usable(item.get("image_url")):
                        n += 1
                elif usable(item):
                    n += 1
        out[s["symbol_id"]] = n
    return out


# ---------------------------------------------------------------------- #
# 记录归一化
# ---------------------------------------------------------------------- #
def normalise(record: Dict[str, Any], gt: Dict[str, Any], mode: str,
              gate: str, kb: SymbolKnowledgeBase, kb_vocab: List[str],
              ref_counts: Dict[str, int]) -> Dict[str, Any]:
    cands = record.get("topk_candidates") or []
    pred = record.get("pred_symbol", "") or ""
    pred_is_unknown = bool(record.get("unknown_symbol")) or "unknown_symbol" in pred.lower()
    gt_ids = [i for i in gt.get("gt_symbol_ids", []) if i]
    sample_type = gt.get("sample_type", "known")
    cand_ids = [c.get("symbol_id") for c in cands]

    rank = next((i + 1 for i, cid in enumerate(cand_ids) if cid in gt_ids), None)
    top1 = cands[0] if cands else {}
    top2 = cands[1] if len(cands) > 1 else {}

    if sample_type == "known":
        correct = (not pred_is_unknown) and hit_gt_symbol(pred, gt.get("gt_symbols", []), kb)
    else:
        correct = pred_is_unknown

    identity_ev = record.get("identity_evidence") or []
    top1_identity = next((e for e in identity_ev
                          if e.get("symbol_id") == top1.get("symbol_id")), {})

    # 图像证据可得性：GT 符号是否有真实参考图（image 模式的关键约束）
    if mode in ("image", "multimodal", "multimodal_controlled") and gt_ids:
        image_status = "available" if ref_counts.get(gt_ids[0], 0) > 0 else "unavailable"
    elif mode in ("image", "multimodal", "multimodal_controlled"):
        image_status = "not_applicable_unknown_gt"
    else:
        image_status = "not_used"

    return {
        "video_id": gt["video_id"],
        "mode": mode,
        "gate": gate,
        "method": f"{MODE_LABEL.get(mode, mode)}",
        "ground_truth_symbol": ";".join(gt.get("gt_symbols", [])),
        "gt_symbol_ids": ";".join(gt_ids),
        "sample_type": sample_type,
        "gt_dimension_code": gt.get("gt_dimension_code", ""),
        "top1_candidate": top1.get("canonical_name", ""),
        "top1_symbol_id": top1.get("symbol_id", ""),
        "top1_dimension": top1.get("dimension_code", ""),
        "top1_score": top1.get("score", ""),
        "top2_candidate": top2.get("canonical_name", ""),
        "top2_score": top2.get("score", ""),
        "text_score": top1.get("text_score", ""),
        "image_score": top1.get("image_score", ""),
        "fusion_score": top1.get("fusion_score", ""),
        "top5_symbols": " > ".join(c.get("canonical_name", "") for c in cands[:5]),
        "identity_evidence_level": top1_identity.get("identity_evidence_level", ""),
        "identity_evidence_detail": "|".join(
            f"{e.get('canonical_name')}:{e.get('identity_evidence_level')}"
            for e in identity_ev) if identity_ev else "",
        "identity_gate_pass": record.get("identity_gate_pass"),
        "identity_passed_symbols": ";".join(record.get("identity_passed_symbol_ids") or []),
        "existing_gate_level": record.get("gate_level", ""),
        "effective_gate_level": record.get("effective_gate_level") or record.get("gate_level", ""),
        "image_evidence_status": image_status,
        "prediction": pred,
        "pred_dimension": record.get("pred_dimension", ""),
        "rejected": pred_is_unknown,
        "correct": bool(correct),
        "hallucination": (not pred_is_unknown) and bool(pred) and is_hallucination(pred, kb_vocab),
        "dimension_correct": dimension_hit(record.get("pred_dimension", ""),
                                           gt.get("gt_dimension_code", "")),
        "rank": rank,
        "recall@1": (1 if rank == 1 else 0) if gt_ids else None,
        "recall@5": (1 if rank and rank <= 5 else 0) if gt_ids else None,
        "mrr": (1.0 / rank if rank else 0.0) if gt_ids else None,
        "error_type": classify_error(sample_type, pred_is_unknown, correct, gt_ids,
                                     cand_ids, rank, record, mode),
        "kb_coverage": gt.get("kb_coverage", ""),
    }


def classify_error(sample_type: str, pred_is_unknown: bool, correct: bool,
                   gt_ids: List[str], cand_ids: List[str], rank: Optional[int],
                   record: Dict[str, Any], mode: str) -> str:
    if correct:
        return ""
    if sample_type == "known":
        if pred_is_unknown:
            return "false_rejection"
        if not gt_ids:
            return "final_selection_error"
        if rank is None:
            return "retrieval_error"
        if rank > 1:
            return "ranking_error"
        return "final_selection_error"
    # unknown 样本被错误放行
    if mode == "free":
        return "hard_unknown_false_accept" if sample_type == "hard_unknown" \
            else "easy_unknown_false_accept"
    if record.get("identity_gate_pass") is False:
        return "insufficient_identity_evidence"
    return "hard_unknown_false_accept" if sample_type == "hard_unknown" \
        else "easy_unknown_false_accept"


# ---------------------------------------------------------------------- #
# 指标汇总
# ---------------------------------------------------------------------- #
def summarise(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    known = [r for r in rows if r["sample_type"] == "known"]
    hard = [r for r in rows if r["sample_type"] == "hard_unknown"]
    easy = [r for r in rows if r["sample_type"] == "easy_unknown"]
    unknown = hard + easy
    n = len(rows)

    def rate(num, den):
        return round(num / den, 4) if den else None

    n_known = len(known)
    return {
        "n_samples": n,
        "n_known": n_known,
        "n_easy_unknown": len(easy),
        "n_hard_unknown": len(hard),
        "recall@1": rate(sum(1 for r in known if r["recall@1"] == 1), n_known),
        "recall@5": rate(sum(1 for r in known if r["recall@5"] == 1), n_known),
        "mrr": round(sum(r["mrr"] for r in known) / n_known, 4) if n_known else None,
        "symbol_accuracy": rate(sum(1 for r in known if r["correct"]), n_known),
        "dimension_accuracy": rate(sum(1 for r in known if r["dimension_correct"]), n_known),
        "known_accept_rate": rate(sum(1 for r in known if not r["rejected"]), n_known),
        "false_rejection_rate": rate(sum(1 for r in known if r["rejected"]), n_known),
        "easy_unknown_rejection_rate": rate(sum(1 for r in easy if r["rejected"]), len(easy)),
        "hard_unknown_rejection_rate": rate(sum(1 for r in hard if r["rejected"]), len(hard)),
        "unknown_rejection_rate": rate(sum(1 for r in unknown if r["rejected"]), len(unknown)),
        "hallucination_rate": rate(sum(1 for r in rows if r["hallucination"]), n),
        "unknown_false_accept_rate": rate(sum(1 for r in unknown if not r["rejected"]), len(unknown)),
    }


def write_csv(path: str, rows: List[Dict[str, Any]], cols: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------------- #
# 主流程
# ---------------------------------------------------------------------- #
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    kb = SymbolKnowledgeBase()
    kb_vocab = build_kb_vocab(kb)
    ref_counts = reference_image_map(kb)
    gt_items = load_jsonl(GT_PATH)
    gt_map = {g["video_id"]: g for g in gt_items}

    exp1 = load_merged(EXP1_PATHS)
    exp2 = load_merged(EXP2_PATHS)
    print(f"[数据] GT={len(gt_items)} 实验一={len(exp1)} 实验二={len(exp2)}")

    # 基线（Existing Gate）：实验一全量记录
    rows_base: List[Dict[str, Any]] = []
    for rec in exp1:
        gt = gt_map.get(rec["video_id"])
        if not gt:
            continue
        rows_base.append(normalise(rec, gt, rec.get("mode", ""), GATE_BASELINE,
                                   kb, kb_vocab, ref_counts))

    # Proposed（+Identity Gate）：实验二覆盖 4 个 KB 模式；free 模式不接入门控，
    # 直接复用实验一 free 记录（同一批视频、同一 Pass-1 缓存、同一参数）
    rows_ident: List[Dict[str, Any]] = []
    ident_keys = {(r["video_id"], r["mode"]) for r in exp2}
    for rec in exp2:
        gt = gt_map.get(rec["video_id"])
        if not gt:
            continue
        rows_ident.append(normalise(rec, gt, rec.get("mode", ""), GATE_IDENTITY,
                                    kb, kb_vocab, ref_counts))
    if exp2:
        for r in rows_base:
            if r["mode"] == "free":
                rows_ident.append(dict(r, gate=GATE_IDENTITY))

    all_rows = rows_base + rows_ident
    print(f"[行数] baseline={len(rows_base)} identity={len(rows_ident)} 合计={len(all_rows)}")

    # ---------------- 逐视频明细 ----------------
    detail_cols = ["video_id", "sample_type", "mode", "gate", "method",
                   "ground_truth_symbol", "gt_symbol_ids", "gt_dimension_code",
                   "top1_candidate", "top1_symbol_id", "top1_score",
                   "top2_candidate", "top2_score",
                   "text_score", "image_score", "fusion_score", "top5_symbols",
                   "identity_evidence_level", "identity_evidence_detail",
                   "identity_gate_pass", "identity_passed_symbols",
                   "existing_gate_level", "effective_gate_level",
                   "image_evidence_status",
                   "prediction", "pred_dimension", "rejected", "correct",
                   "dimension_correct", "hallucination", "rank", "error_type"]
    write_csv(os.path.join(OUT_DIR, "final30_predictions.csv"), all_rows, detail_cols)

    # ---------------- 实验一 ----------------
    exp1_summary_rows = []
    for mode in MODES:
        s = summarise([r for r in rows_base if r["mode"] == mode])
        s.update({"method": MODE_LABEL[mode], "mode": mode, "gate": GATE_BASELINE})
        exp1_summary_rows.append(s)
    exp1_cols = ["method", "mode", "n_samples", "n_known", "recall@1", "recall@5", "mrr",
                 "symbol_accuracy", "dimension_accuracy", "hallucination_rate",
                 "unknown_false_accept_rate", "unknown_rejection_rate"]
    write_csv(os.path.join(OUT_DIR, "experiment1_results.csv"), exp1_summary_rows, exp1_cols)

    main1 = [{"Method": r["method"], "Recall@1": r["recall@1"], "Recall@5": r["recall@5"],
              "MRR": r["mrr"], "Symbol Accuracy": r["symbol_accuracy"],
              "Dimension Accuracy": r["dimension_accuracy"],
              "Hallucination Rate": r["hallucination_rate"]} for r in exp1_summary_rows]
    write_csv(os.path.join(OUT_DIR, "experiment1_main_table.csv"), main1,
              ["Method", "Recall@1", "Recall@5", "MRR", "Symbol Accuracy",
               "Dimension Accuracy", "Hallucination Rate"])

    # ---------------- 实验二 ----------------
    exp2_summary_rows = []
    for gate, rows in ((GATE_BASELINE, rows_base), (GATE_IDENTITY, rows_ident)):
        if not rows:
            continue
        s = summarise(rows)
        s.update({"method": GATE_LABEL[gate], "gate": gate, "scope": "all_modes"})
        exp2_summary_rows.append(s)
        for mode in MODES:
            ms = summarise([r for r in rows if r["mode"] == mode])
            ms.update({"method": f"{GATE_LABEL[gate]} @ {MODE_LABEL[mode]}",
                       "gate": gate, "mode": mode, "scope": "per_mode"})
            exp2_summary_rows.append(ms)
        ks = summarise([r for r in rows if r["mode"] != "free"])
        ks.update({"method": f"{GATE_LABEL[gate]} (KB modes only)",
                   "gate": gate, "scope": "kb_modes_only"})
        exp2_summary_rows.append(ks)
    exp2_cols = ["method", "gate", "scope", "mode", "n_samples", "n_known",
                 "symbol_accuracy", "known_accept_rate",
                 "easy_unknown_rejection_rate", "hard_unknown_rejection_rate",
                 "unknown_rejection_rate", "false_rejection_rate", "hallucination_rate"]
    write_csv(os.path.join(OUT_DIR, "experiment2_results.csv"), exp2_summary_rows, exp2_cols)

    main2 = []
    for gate, rows in ((GATE_BASELINE, rows_base), (GATE_IDENTITY, rows_ident)):
        if not rows:
            continue
        s = summarise(rows)
        main2.append({"Method": GATE_LABEL[gate],
                      "Known Acc": s["symbol_accuracy"],
                      "Known Accept": s["known_accept_rate"],
                      "Easy Unknown Reject": s["easy_unknown_rejection_rate"],
                      "Hard Unknown Reject": s["hard_unknown_rejection_rate"],
                      "False Reject": s["false_rejection_rate"],
                      "Hallucination": s["hallucination_rate"]})
    write_csv(os.path.join(OUT_DIR, "experiment2_main_table.csv"), main2,
              ["Method", "Known Acc", "Known Accept", "Easy Unknown Reject",
               "Hard Unknown Reject", "False Reject", "Hallucination"])

    # ---------------- Hard Unknown 单独分析 ----------------
    hard_rows = []
    for r in all_rows:
        if r["sample_type"] != "hard_unknown":
            continue
        hard_rows.append({
            "video_id": r["video_id"], "gate": r["gate"], "mode": r["mode"],
            "ground_truth": r["ground_truth_symbol"],
            "top1_candidate": r["top1_candidate"],
            "top1_score": r["top1_score"],
            "text_score": r["text_score"], "image_score": r["image_score"],
            "fusion_score": r["fusion_score"],
            "category_evidence": (f"same_dimension={r['top1_dimension']}; "
                                  f"type_relation=同维度同类型近邻候选"),
            "identity_evidence": r["identity_evidence_level"] or "none",
            "identity_evidence_detail": r["identity_evidence_detail"],
            "existing_gate_result": r["existing_gate_level"],
            "identity_gate_result": ("pass" if r["identity_gate_pass"] else
                                     ("reject" if r["identity_gate_pass"] is False
                                      else "not_applied")),
            "prediction": r["prediction"],
            "rejected": r["rejected"],
            "correct": r["correct"],
            "error_type": r["error_type"] or "correctly_rejected",
        })
    write_csv(os.path.join(OUT_DIR, "hard_unknown_case_analysis.csv"), hard_rows,
              ["video_id", "gate", "mode", "ground_truth", "top1_candidate", "top1_score",
               "text_score", "image_score", "fusion_score", "category_evidence",
               "identity_evidence", "identity_evidence_detail",
               "existing_gate_result", "identity_gate_result", "prediction",
               "rejected", "correct", "error_type"])

    # ---------------- 绘图数据 ----------------
    plot_rows = []
    for mode in ["text", "image", "multimodal", "multimodal_controlled"]:
        s = next(r for r in exp1_summary_rows if r["mode"] == mode)
        for metric in ("recall@1", "recall@5", "mrr"):
            plot_rows.append({"method": MODE_LABEL[mode], "mode": mode,
                              "metric": metric, "value": s[metric]})
    write_csv(os.path.join(OUT_DIR, "retrieval_metrics_plot.csv"), plot_rows,
              ["method", "mode", "metric", "value"])

    halluc_rows = [{"method": r["method"], "mode": r["mode"],
                    "hallucination_rate": r["hallucination_rate"]}
                   for r in exp1_summary_rows]
    write_csv(os.path.join(OUT_DIR, "hallucination_comparison.csv"), halluc_rows,
              ["method", "mode", "hallucination_rate"])

    gate_rows = []
    for gate, rows in ((GATE_BASELINE, rows_base), (GATE_IDENTITY, rows_ident)):
        if not rows:
            continue
        s = summarise(rows)
        gate_rows.append({"method": GATE_LABEL[gate], "gate": gate, "scope": "all_modes",
                          "known_acc": s["symbol_accuracy"],
                          "hard_unknown_reject": s["hard_unknown_rejection_rate"],
                          "easy_unknown_reject": s["easy_unknown_rejection_rate"],
                          "false_reject": s["false_rejection_rate"],
                          "hallucination": s["hallucination_rate"]})
        for mode in MODES:
            ms = summarise([r for r in rows if r["mode"] == mode])
            gate_rows.append({"method": f"{GATE_LABEL[gate]} @ {MODE_LABEL[mode]}",
                              "gate": gate, "mode": mode, "scope": "per_mode",
                              "known_acc": ms["symbol_accuracy"],
                              "hard_unknown_reject": ms["hard_unknown_rejection_rate"],
                              "easy_unknown_reject": ms["easy_unknown_rejection_rate"],
                              "false_reject": ms["false_rejection_rate"],
                              "hallucination": ms["hallucination_rate"]})
        ks = summarise([r for r in rows if r["mode"] != "free"])
        gate_rows.append({"method": f"{GATE_LABEL[gate]} (KB modes only)",
                          "gate": gate, "scope": "kb_modes_only", "mode": "",
                          "known_acc": ks["symbol_accuracy"],
                          "hard_unknown_reject": ks["hard_unknown_rejection_rate"],
                          "easy_unknown_reject": ks["easy_unknown_rejection_rate"],
                          "false_reject": ks["false_rejection_rate"],
                          "hallucination": ks["hallucination_rate"]})
    write_csv(os.path.join(OUT_DIR, "gate_comparison.csv"), gate_rows,
              ["method", "gate", "scope", "mode", "known_acc", "hard_unknown_reject",
               "easy_unknown_reject", "false_reject", "hallucination"])

    score_rows = [{"video_id": r["video_id"], "sample_type": r["sample_type"],
                   "mode": r["mode"], "gate": r["gate"],
                   "fusion_score": r["fusion_score"],
                   "top1_score": r["top1_score"],
                   "text_score": r["text_score"], "image_score": r["image_score"]}
                  for r in all_rows]
    write_csv(os.path.join(OUT_DIR, "score_distribution.csv"), score_rows,
              ["video_id", "sample_type", "mode", "gate", "fusion_score",
               "top1_score", "text_score", "image_score"])

    # ---------------- 报告 ----------------
    write_report(gt_items, kb, ref_counts, exp1_summary_rows, exp2_summary_rows,
                 rows_base, rows_ident, all_rows, hard_rows)
    print(f"[完成] 产物目录: {OUT_DIR}")


# ---------------------------------------------------------------------- #
# 报告生成
# ---------------------------------------------------------------------- #
def fmt(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def md_table(headers: List[str], rows: List[List[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(fmt(c) for c in r) + " |")
    return "\n".join(lines)


def write_report(gt_items, kb, ref_counts, exp1_summary, exp2_summary,
                 rows_base, rows_ident, all_rows, hard_rows):
    n_total = len(gt_items)
    st = Counter(g["sample_type"] for g in gt_items)
    dim = Counter(g.get("gt_dimension_code", "") for g in gt_items)
    sym = Counter(";".join(g.get("gt_symbols", [])) for g in gt_items)
    kb_dim = Counter(s.get("dimension_code", "") for s in kb.symbols)
    kb_ref = sum(1 for v in ref_counts.values() if v > 0)
    known_gt = [g for g in gt_items if g.get("gt_symbol_ids")]
    known_with_img = sum(1 for g in known_gt if ref_counts.get(g["gt_symbol_ids"][0], 0) > 0)

    L: List[str] = []
    L.append("# 创新点2 正式实验报告：知识增强多模态检索 + 身份证据拒识门控\n")
    L.append("> 全部数字由 `scripts/innovation2/analyze_final30.py` 从冻结 GT 与落盘实验结果自动计算，"
             "无手工填值。\n")

    # ---------------- 1. 实验设置 ----------------
    L.append("\n## 1. 实验设置\n")
    L.append(f"- 数据集：`experiments/innovation2/data/videos/` 中 {n_total} 条人工核验文化视频"
             f"（30 个素材 + 1 条同场景重复拍摄），GT 冻结于 "
             "`experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl`，"
             "人审表见 `experiments/innovation2/data/cultural_eval/cultural_eval_30.csv`，`review_status=frozen`。")
    L.append(f"- 样本类型分布：Known {st.get('known', 0)} / "
             f"Easy Unknown {st.get('easy_unknown', 0)} / "
             f"Hard Unknown {st.get('hard_unknown', 0)}。")
    L.append(f"- 知识库：v2 正式 KB 共 {len(kb.symbols)} 个文化符号，"
             f"参考图覆盖 {kb_ref}/{len(kb.symbols)} 个符号；"
             f"31 条视频中的 Known 样本有 {known_with_img}/{len(known_gt)} 条其 GT 符号具备可用真实参考图。")
    L.append("- 五维分布（样本 / KB）：" + "，".join(
        f"{d} {dim.get(d, 0)} / {kb_dim.get(d, 0)}"
        for d in ["ANCIENT", "RED", "FOLK", "TECH", "MODERN"]) + "。")
    L.append("- 模型与参数：标注模型 GLM-4V（API），图像编码器 CLIP ViT-B/32；"
             "统一 `top_k=5`、关键帧采样 `num_frames=4`、Pass-1 场景描述在同批视频内跨模式复用。")
    L.append("- 融合权重：`fusion_score = α·text_score + (1-α)·image_score`，"
             "α=0.5（Text+Image 融合，取自既有配置，未在 test 集上调）；"
             "Image 模式 α=0（纯图像分），Text 模式纯文本不进融合。")
    L.append("- 图像证据：Image / Multimodal 的图像分严格来自「视频关键帧 CLIP embedding」"
             "与「KB 真实参考图 CLIP embedding」的余弦相似度；"
             "无真实参考图的符号不参与图像排序（图像分缺失），"
             "在逐条明细中标记 `image_evidence_status=unavailable`，"
             "不使用文本描述模拟图像检索。")
    L.append("- Gate 阈值：来自验证集网格搜索产物 `experiments/innovation2/data/eval/rejection_thresholds.json`"
             "（v2-30sucai：text score_thr=0.5，image/multimodal score_thr=0.4，"
             "margin_thr=0，require_keywords=true），未在 test 集调整。"
             "Identity Evidence Gate 配置为 `config/identity_evidence_gate.json`，"
             "其强证据仅接受 canonical/alias 完整实体命中或 KB 独特视觉属性命中。")
    L.append("\n### 1.1 每个文化符号的样本数\n")
    L.append(md_table(["文化符号", "样本数"],
                      [[k, v] for k, v in sorted(sym.items(), key=lambda x: -x[1])]))
    L.append("\n### 1.2 维度分布\n")
    L.append(md_table(["维度码", "样本数"], [[d, dim.get(d, 0)]
                                        for d in ["ANCIENT", "RED", "FOLK", "TECH", "MODERN"]]))

    # ---------------- 2. 实验一 ----------------
    L.append("\n## 2. 实验一：知识增强与多模态检索对比\n")
    L.append(f"评估口径：Known {st.get('known', 0)} 条参与 Recall@1/Recall@5/MRR/"
             "Symbol Accuracy/Dimension Accuracy；Hallucination Rate 在全部 "
             f"{n_total} 条上统计（输出具体符号但完全不含任何 KB 词表项 = 编造）。"
             "Hallucination Rate 基于 KB 词表子串判定，因此 Free 模式下模型输出整句描述时"
             "只要句中出现任一 KB 词条即不计为幻觉，该指标偏保守。\n")
    L.append(md_table(["Method", "Recall@1", "Recall@5", "MRR", "Symbol Accuracy",
                       "Dimension Accuracy", "Hallucination Rate"],
                      [[r["method"], r["recall@1"], r["recall@5"], r["mrr"],
                        r["symbol_accuracy"], r["dimension_accuracy"],
                        r["hallucination_rate"]] for r in exp1_summary]))

    best_r1 = max(exp1_summary, key=lambda r: (r["recall@1"] or 0))
    best_mrr = max(exp1_summary, key=lambda r: (r["mrr"] or 0))
    text_s = next(r for r in exp1_summary if r["mode"] == "text")
    img_s = next(r for r in exp1_summary if r["mode"] == "image")
    mm_s = next(r for r in exp1_summary if r["mode"] == "multimodal")
    ctl_s = next(r for r in exp1_summary if r["mode"] == "multimodal_controlled")
    free_s = next(r for r in exp1_summary if r["mode"] == "free")

    L.append("\n**最佳检索方法**：")
    L.append(f"- Recall@1 最高：{best_r1['method']}（{fmt(best_r1['recall@1'])}）；"
             f"MRR 最高：{best_mrr['method']}（{fmt(best_mrr['mrr'])}）。")
    L.append(f"- Text vs Image：Text Recall@1={fmt(text_s['recall@1'])} vs "
             f"Image Recall@1={fmt(img_s['recall@1'])}；"
             f"MRR {fmt(text_s['mrr'])} vs {fmt(img_s['mrr'])}。"
             "纯 CLIP ViT-B/32 图像-图像检索在本数据集上几乎不具备判别力"
             f"（Recall@5 仅 {fmt(img_s['recall@5'])}）。")
    L.append(f"- Multimodal vs Text：Multimodal Recall@1={fmt(mm_s['recall@1'])} "
             f"（Text {fmt(text_s['recall@1'])}），MRR {fmt(mm_s['mrr'])} "
             f"（Text {fmt(text_s['mrr'])}），Recall@5 {fmt(mm_s['recall@5'])} "
             f"（Text {fmt(text_s['recall@5'])}）。"
             "融合在检索排序上有稳定增益，但 Symbol Accuracy 未同步提升"
             f"（Multimodal {fmt(mm_s['symbol_accuracy'])} vs Text {fmt(text_s['symbol_accuracy'])}）。")
    L.append(f"- Controlled 与 Hallucination：Multimodal Hallucination="
             f"{fmt(mm_s['hallucination_rate'])} → Controlled="
             f"{fmt(ctl_s['hallucination_rate'])}；"
             + (f"Symbol Accuracy 由 {fmt(mm_s['symbol_accuracy'])} 降至 "
                f"{fmt(ctl_s['symbol_accuracy'])}（闭集约束把部分非候选输出改写成 unknown_symbol）。"
                if ctl_s['symbol_accuracy'] < mm_s['symbol_accuracy'] else
                f"Symbol Accuracy 保持 {fmt(ctl_s['symbol_accuracy'])} 不变"
                "（该批次中多模态输出本就落在闭集候选内，故幻觉下降未牺牲符号准确率）。"))
    L.append(f"- Free 基线：Symbol Accuracy {fmt(free_s['symbol_accuracy'])}，"
             f"Recall@1 {fmt(free_s['recall@1'])}（无检索，不存在候选排序），"
             f"Hallucination {fmt(free_s['hallucination_rate'])}。"
             "Free 的 Symbol Accuracy 来自输出整句描述与 GT 别名的子串匹配，"
             "不能等同于闭集检索能力。")

    # ---------------- 3. 实验二 ----------------
    L.append("\n## 3. 实验二：Unknown 拒识与 Identity Evidence Gate\n")
    L.append("Baseline = Existing Gate（三信号：检索分数、Top1-Top2 分差、KB 词表/场景负信号）；"
             "Proposed = Existing Gate 放行后再要求每个候选具备身份级证据"
             "（canonical/alias 完整实体命中或 KB 独特视觉属性命中），"
             "全部候选无身份证据则整条样本拒识。两种门控使用同一批视频、"
             "同一检索结果来源与同一 Pass-1 缓存；Free 模式不接入门控，两列共用同一结果。\n")
    main2_rows = []
    for gate, rows in ((GATE_BASELINE, rows_base), (GATE_IDENTITY, rows_ident)):
        s = summarise(rows)
        main2_rows.append([GATE_LABEL[gate], s["symbol_accuracy"], s["known_accept_rate"],
                           s["easy_unknown_rejection_rate"],
                           s["hard_unknown_rejection_rate"],
                           s["false_rejection_rate"], s["hallucination_rate"]])
    L.append(md_table(["Method", "Known Acc", "Known Accept", "Easy Unknown Reject",
                       "Hard Unknown Reject", "False Reject", "Hallucination"], main2_rows))

    # 仅 KB 模式聚合（排除不接入门控的 Free，避免稀释门控效果）
    kb_rows = []
    for gate, rows in ((GATE_BASELINE, rows_base), (GATE_IDENTITY, rows_ident)):
        s = summarise([r for r in rows if r["mode"] != "free"])
        kb_rows.append([GATE_LABEL[gate], s["symbol_accuracy"], s["known_accept_rate"],
                        s["easy_unknown_rejection_rate"], s["hard_unknown_rejection_rate"],
                        s["false_rejection_rate"], s["hallucination_rate"]])
    L.append("\n上表为 5 模式合并口径（含不接入门控的 Free，会稀释门控效果）。"
             "下表仅聚合 4 个接入门控的 KB 模式（Text/Image/Multimodal/Controlled）：\n")
    L.append(md_table(["Method (KB modes only)", "Known Acc", "Known Accept",
                       "Easy Unknown Reject", "Hard Unknown Reject", "False Reject",
                       "Hallucination"], kb_rows))

    s_b_kb = summarise([r for r in rows_base if r["mode"] != "free"])
    s_i_kb = summarise([r for r in rows_ident if r["mode"] != "free"])
    L.append("\n**关键发现（KB 模式聚合）**：")
    L.append(f"- Hard Unknown 拒识率 {fmt(s_b_kb['hard_unknown_rejection_rate'])} → "
             f"{fmt(s_i_kb['hard_unknown_rejection_rate'])}，"
             f"Known 接受率 {fmt(s_b_kb['known_accept_rate'])} → "
             f"{fmt(s_i_kb['known_accept_rate'])}，"
             f"Known 符号准确率 {fmt(s_b_kb['symbol_accuracy'])} → "
             f"{fmt(s_i_kb['symbol_accuracy'])}。"
             "Identity Gate 确实提高了 Hard Unknown 拒识，但同时把大量 Known 样本"
             "误拒，二者是同一机制的两面，不能只报收益。")
    L.append("- Image 模式是主要拖累：Identity Gate 要求候选的规范名/别名出现在"
             "Pass-1 场景描述中，而纯图像检索的候选来自 CLIP 相似度、其名称几乎不会"
             "出现在场景描述里，因此该模式下 Identity Gate 退化为「全部拒识」"
             "（Known 全部 false rejection，准确率 0）。这说明身份证据门控只能与"
             "文本侧证据同源的检索模式配合，不能直接套在纯图像检索上。")
    L.append("- Text/Multimodal 模式下 Identity Gate 的收益有限：Hard Unknown 中"
             "神武门、人民大会堂两条视频的画面主体被 VLM 明确写成「故宫」「天安门广场」，"
             "这两个父实体/近邻实体在 KB 中存在，于是产生了合法的强身份证据并被放行——"
             "这正是「高相似但不是同一文化符号」的错误放行，文本身份证据无法区分。")
    L.append("- 两种门控的对比包含一次独立的 GLM-4V 采样（Prompt 不同导致重新调用），"
             "未做多次采样平均，因此单条样本的差异含采样噪声；结论只应看聚合趋势。\n")

    L.append("\n### 3.1 分模式结果\n")
    per_mode_rows = []
    for gate, rows in ((GATE_BASELINE, rows_base), (GATE_IDENTITY, rows_ident)):
        for mode in MODES:
            s = summarise([r for r in rows if r["mode"] == mode])
            per_mode_rows.append([GATE_LABEL[gate], MODE_LABEL[mode], s["symbol_accuracy"],
                                  s["known_accept_rate"],
                                  s["hard_unknown_rejection_rate"],
                                  s["easy_unknown_rejection_rate"],
                                  s["false_rejection_rate"], s["hallucination_rate"]])
    L.append(md_table(["Gate", "Mode", "Known Acc", "Known Accept", "Hard Unknown Reject",
                       "Easy Unknown Reject", "False Reject", "Hallucination"], per_mode_rows))

    # ---------------- 4. Hard Unknown ----------------
    L.append("\n## 4. Hard Unknown 专项分析\n")
    hard_ids = sorted({r["video_id"] for r in hard_rows})
    L.append(f"Hard Unknown 共 {len(hard_ids)} 条（{'、'.join(hard_ids)}）："
             "真实符号不在 KB，但 KB 中存在同维度/父实体/视觉高度相似的候选。"
             "此类样本是「高相似但非同一文化符号」错误放行的主要来源。\n")
    by_key = {(r["video_id"], r["gate"], r["mode"]): r for r in hard_rows}
    show_rows = []
    for vid in hard_ids:
        for mode in [m for m in MODES if m != "free"]:
            b = by_key.get((vid, GATE_BASELINE, mode), {})
            i = by_key.get((vid, GATE_IDENTITY, mode), {})
            show_rows.append([vid, MODE_LABEL[mode],
                              b.get("top1_candidate", ""), b.get("fusion_score", ""),
                              i.get("identity_evidence", ""),
                              b.get("existing_gate_result", ""),
                              i.get("identity_gate_result", ""),
                              "是" if b.get("rejected") else "否",
                              "是" if i.get("rejected") else "否",
                              i.get("error_type", "")])
    L.append(md_table(["视频", "模式", "Top1 候选", "Top1 主分数", "Identity Evidence(+Gate)",
                       "Existing Gate", "Identity Gate", "基线拒识", "Identity 拒识",
                       "错误类型"], show_rows))

    for gate, rows in ((GATE_BASELINE, rows_base), (GATE_IDENTITY, rows_ident)):
        hard = [r for r in rows if r["sample_type"] == "hard_unknown"]
        n = len(hard)
        rej = sum(1 for r in hard if r["rejected"])
        L.append(f"- {GATE_LABEL[gate]}：Hard Unknown 拒识 {rej}/{n}"
                 f"（{fmt(rej / n if n else None)}）。")
    L.append("")

    # ---------------- 5. Error Analysis ----------------
    L.append("\n## 5. Error Analysis\n")
    err_counter = Counter(r["error_type"] for r in all_rows if r["error_type"])
    L.append(md_table(["错误类型", "出现次数"],
                      [[k, v] for k, v in err_counter.most_common()]))
    L.append("\n错误类型定义：`retrieval_error`（GT 未进 Top-5）、`ranking_error`"
             "（GT 在 Top-5 但非 Top-1）、`final_selection_error`（GT 已在 Top-1 但模型选了别的符号）、"
             "`false_rejection`（Known 被拒识）、`hard_unknown_false_accept`/"
             "`easy_unknown_false_accept`（Unknown 被错误放行为具体符号）、"
             "`insufficient_identity_evidence`（Identity Gate 拒识但仍输出符号，理论不应出现，用于审计）。\n")

    # 图像证据缺失
    img_na = [r for r in all_rows if r["image_evidence_status"] == "unavailable"]
    if img_na:
        L.append(f"- `missing_image_evidence`：{len(img_na)} 条记录（"
                 f"{len({r['video_id'] for r in img_na})} 条视频）的 GT 符号在 KB 中"
                 "没有可用的真实参考图，其图像分缺失（不参与图像排序，记为 0），"
                 "这些样本的图像检索在原理上不可能命中，已在明细中标记 "
                 "`image_evidence_status=unavailable`，未使用文本编码伪造图像证据。\n")

    # ---------------- 6. 结论 ----------------
    L.append("\n## 6. 最终结论\n")
    s_b = summarise(rows_base)
    s_i = summarise(rows_ident)
    L.append(f"1. 本实验基于 {n_total} 条人工核验文化视频（Known {st.get('known', 0)} / "
             f"Easy Unknown {st.get('easy_unknown', 0)} / Hard Unknown {st.get('hard_unknown', 0)}），"
             "样本量小且类别不均衡，作为方法验证集而非大规模评测集，"
             "结论不宜外推为通用性能排名。")
    L.append(f"2. 检索层面，文本关键词检索是主要有效信号（Recall@1 "
             f"{fmt(text_s['recall@1'])}）；CLIP ViT-B/32 纯图像检索在本域几乎不可用"
             f"（Recall@1 {fmt(img_s['recall@1'])}），文本+图像融合带来小幅稳定增益"
             f"（Recall@1 {fmt(mm_s['recall@1'])}，MRR {fmt(mm_s['mrr'])}）。"
             "Multimodal 优于 Text 主要体现在候选排序，而非最终符号准确率。")
    L.append(f"3. Controlled 输出约束把幻觉率由 {fmt(mm_s['hallucination_rate'])} 降到 "
             f"{fmt(ctl_s['hallucination_rate'])}，"
             + ("Known 符号准确率不变"
                f"（{fmt(ctl_s['symbol_accuracy'])}），即本批次中闭集约束只削减了幻觉、"
                "未牺牲已知符号召回。"
                if ctl_s['symbol_accuracy'] >= mm_s['symbol_accuracy'] else
                f"代价是 Known 符号准确率下降（{fmt(mm_s['symbol_accuracy'])} → "
                f"{fmt(ctl_s['symbol_accuracy'])}），即闭集约束用召回换取了可靠性。"))
    L.append(f"4. Identity Evidence Gate 把整体 Hard Unknown 拒识率由 "
             f"{fmt(s_b['hard_unknown_rejection_rate'])} 变为 "
             f"{fmt(s_i['hard_unknown_rejection_rate'])}，已知符号接受率由 "
             f"{fmt(s_b['known_accept_rate'])} 变为 {fmt(s_i['known_accept_rate'])}，"
             f"Known 符号准确率 {fmt(s_b['symbol_accuracy'])} → "
             f"{fmt(s_i['symbol_accuracy'])}。"
             "该门控的收益与代价均明确存在，不应笼统声称单向提升。"
             "由于当前 KB 尚无 OCR / 参考图级身份证据，Image 模式会被全拒识，"
             "净效果在本数据上为负（Known 准确率下降），"
             "因此 Identity Evidence Gate 目前只能作为「可审计的候选级证据层」"
             "而非可直接上线的拒识策略。")
    L.append(f"5. 剩余错误集中在两类：一是 Known 样本在图像证据缺失或纯图像检索下"
             f"被拒识（false_rejection），二是 Hard Unknown 在场景描述中确实出现了"
             f"父实体/近邻实体名称时被身份证据误认为同一符号"
             f"（hard_unknown_false_accept）。后者说明「文本身份证据」无法替代图像级/OCR级"
             "身份证据，是后续工作方向。")

    with open(os.path.join(OUT_DIR, "innovation2_final_experiment_report.md"),
              "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
