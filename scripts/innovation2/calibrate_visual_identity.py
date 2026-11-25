"""在 validation set 上标定视觉身份证据阈值（绝不使用 31 条正式 test）。

validation 集：experiments/innovation2/data/eval/cultural_ablation_gt.jsonl（6 条视频，与正式 31 条零重叠）。
标定内容：
  max_ref_sim_strong / topk_ref_sim_strong / frame_consistency_strong
  max_ref_sim_supporting / frame_consistency_supporting
输出：config/identity_verifier_v2.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.knowledge.clip_encoder import CLIPEncoder
from src.knowledge.identity_verifier_v2 import VisualIdentityIndex, extract_keyframes
from src.knowledge.symbol_kb import SymbolKnowledgeBase

ROOT = Path(__file__).resolve().parents[2]
VAL_GT = ROOT / "experiments/innovation2/data/eval/cultural_ablation_gt.jsonl"
TEST_GT = ROOT / "experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl"
CONFIG = ROOT / "config/identity_verifier_v2.json"


def main():
    val = [json.loads(l) for l in VAL_GT.open(encoding="utf-8") if l.strip()]
    test_ids = {json.loads(l)["video_id"] for l in TEST_GT.open(encoding="utf-8") if l.strip()}
    assert not ({v["video_id"] for v in val} & test_ids), "validation 与 test 存在重叠"

    kb = SymbolKnowledgeBase()
    clip = CLIPEncoder()
    index = VisualIdentityIndex(kb, clip)

    pos, neg = [], []
    for v in val:
        vid = v["video_id"]
        path = v["video_path"]
        if not os.path.isabs(path):
            path = str(ROOT / path)
        frames = extract_keyframes(path, f"val_{vid}", 4)
        if not frames:
            print(f"[跳过] {vid}: 无法抽帧")
            continue
        matrix, sids = index.frame_matrix(frames)
        for sid in sids:
            ev = index.evidence(matrix, sids, sid)
            row = (ev["max_ref_sim"], ev["topk_ref_sim"], ev["frame_consistency"])
            if sid in set(v.get("gt_symbol_ids") or []):
                pos.append(row)
            else:
                neg.append(row)

    print(f"[标定] 正样本 {len(pos)} 条 / 负样本 {len(neg)} 条（{len(val)} 条 validation 视频）")
    if not pos or not neg:
        raise SystemExit("validation 样本不足，无法标定")

    def balanced_acc(th, pi):
        tpr = sum(1 for p in pos if p[pi] >= th) / len(pos)
        tnr = sum(1 for n in neg if n[pi] < th) / len(neg)
        return (tpr + tnr) / 2

    best_max, best_max_acc = 0.0, -1.0
    for i in range(70, 100):
        th = i / 100
        acc = balanced_acc(th, 0)
        if acc > best_max_acc:
            best_max, best_max_acc = th, acc

    best_topk, best_topk_acc = 0.0, -1.0
    for i in range(60, 100):
        th = i / 100
        acc = balanced_acc(th, 1)
        if acc > best_topk_acc:
            best_topk, best_topk_acc = th, acc

    best_fc, best_fc_acc = 0.0, -1.0
    for i in range(0, 11):
        th = i / 10
        acc = balanced_acc(th, 2)
        if acc > best_fc_acc:
            best_fc, best_fc_acc = th, acc

    neg_max = sorted(n[0] for n in neg)
    supporting = round(neg_max[int(len(neg_max) * 0.95)], 3)
    neg_fc = sorted(n[2] for n in neg)
    supporting_fc = round(neg_fc[int(len(neg_fc) * 0.95)], 1)

    config = {
        "version": "v2.0",
        "calibration": {
            "source": "experiments/innovation2/data/eval/cultural_ablation_gt.jsonl（6 条 validation 视频，与 31 条 test 零重叠）",
            "n_positives": len(pos), "n_negatives": len(neg),
            "balanced_accuracy": {"max_ref_sim": round(best_max_acc, 4),
                                 "topk_ref_sim": round(best_topk_acc, 4),
                                 "frame_consistency": round(best_fc_acc, 4)},
            "negative_95pct": {"max_ref_sim": supporting, "frame_consistency": supporting_fc},
        },
        "visual_identity": {
            "max_ref_sim_strong": best_max,
            "topk_ref_sim_strong": best_topk,
            "frame_consistency_strong": best_fc,
            "max_ref_sim_supporting": supporting,
            "frame_consistency_supporting": supporting_fc,
        },
        "verification": {
            "max_candidates": 3,
            "max_images": 3,
            "num_frames": 4,
            "temperature": 0.0,
            "score_margin_threshold": 0.05,
            "high_fusion_threshold": 0.5,
        },
    }
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[完成] 写入 {CONFIG}")
    print(json.dumps(config["visual_identity"], ensure_ascii=False))


if __name__ == "__main__":
    main()
