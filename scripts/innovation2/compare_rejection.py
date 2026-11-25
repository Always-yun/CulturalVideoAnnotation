"""
拒识优化效果对比分析（gate on vs gate off vs 旧实验）

用法：
    python scripts/innovation2/compare_rejection.py \
        --dirs 旧实验=experiments/innovation2/runs/cultural_ablation/20261015_143003 \
               gate_off=experiments/innovation2/runs/cultural_ablation/gate_off_test \
               gate_on=experiments/innovation2/runs/cultural_ablation/gate_on_test \
        --out experiments/innovation2/runs/cultural_ablation/rejection_comparison.csv

输出：
  1) 模式×指标对比表（含分层指标 gap_reject_rate / hit_symbol_accuracy）
  2) 缺口样本（GT=unknown_symbol）逐样本明细表：预测符号 / 是否拒识 / 门控档位
"""

import os
import sys
import json
import csv
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.experiments.ablation_metrics import build_kb_vocab, compute_mode_summary

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

METRIC_COLS = ["mode", "n_videos", "symbol_accuracy", "dimension_accuracy",
               "hallucination_rate", "unknown_reject_rate",
               "gap_reject_rate", "hit_symbol_accuracy",
               "recall@1", "recall@5", "mrr"]


def parse_arguments():
    p = argparse.ArgumentParser(description="拒识优化效果对比")
    p.add_argument("--dirs", nargs="+", required=True,
                   help="标签=实验目录（可多组）")
    p.add_argument("--out", default=None, help="对比 CSV 输出路径")
    return p.parse_args()


def load_records(path):
    with open(os.path.join(path, "results.json"), "r", encoding="utf-8") as f:
        return json.load(f)["records"]


def main():
    args = parse_arguments()
    kb = SymbolKnowledgeBase()
    vocab = build_kb_vocab(kb)

    # 1) 模式×指标对比表
    rows = []
    per_exp_gap_rows = {}
    for pair in args.dirs:
        label, path = pair.split("=", 1)
        if not os.path.isabs(path):
            path = os.path.join(PROJECT_ROOT, path)
        records = load_records(path)
        modes = list(dict.fromkeys(r["mode"] for r in records))
        for mode in modes:
            mr = [r for r in records if r["mode"] == mode]
            s = compute_mode_summary(mr, kb, vocab)
            rows.append({"experiment": label, **{c: s.get(c, "") for c in METRIC_COLS}})
        # 2) 缺口样本逐样本明细（GT=unknown_symbol）
        for r in records:
            gt_is_unknown = any("unknown_symbol" in g for g in r.get("gt_symbols", []))
            if not gt_is_unknown:
                continue
            per_exp_gap_rows.setdefault(label, []).append({
                "video_id": r["video_id"],
                "mode": r["mode"],
                "gt_dimension": r.get("gt_dimension_code", ""),
                "pred_symbol": (r.get("pred_symbol") or "")[:40],
                "pred_dimension": r.get("pred_dimension", ""),
                "rejected": r.get("unknown_symbol", False),
                "gate_level": r.get("gate_level", ""),
                "gate_reason": (r.get("gate_reason") or "")[:60],
            })

    print("\n===== 模式×指标对比 =====")
    buf = []
    header = ["experiment"] + METRIC_COLS
    buf.append(header)
    for row in rows:
        buf.append([str(row.get(c, "")) for c in header])
    widths = [max(len(r[i]) for r in buf) for i in range(len(header))]
    for r in buf:
        print("  ".join(v.ljust(w) for v, w in zip(r, widths)))

    for label, grows in per_exp_gap_rows.items():
        print(f"\n===== [{label}] 缺口样本明细 =====")
        for g in grows:
            mark = "✓拒识" if g["rejected"] else "✗强配"
            print(f"  {g['video_id']:<14} {g['mode']:<22} {mark} "
                  f"gate={g['gate_level'] or '-':<13} pred={g['pred_symbol']}")

    if args.out:
        out_path = args.out if os.path.isabs(args.out) else os.path.join(PROJECT_ROOT, args.out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["experiment"] + METRIC_COLS)
            w.writeheader()
            w.writerows(rows)
        gap_path = out_path.replace(".csv", "_gap_samples.csv")
        with open(gap_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["experiment", "video_id", "mode", "gt_dimension",
                                              "pred_symbol", "pred_dimension",
                                              "rejected", "gate_level", "gate_reason"])
            w.writeheader()
            for label, grows in per_exp_gap_rows.items():
                for g in grows:
                    w.writerow({"experiment": label, **g})
        print(f"\n[落盘] {out_path}\n[落盘] {gap_path}")


if __name__ == "__main__":
    main()
