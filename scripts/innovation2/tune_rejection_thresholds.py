"""
拒识阈值验证集搜索（创新点2优化：阈值不硬编码，由验证集网格搜索确定）

流程：
  1. 加载 GT v2 验证集（split=val，含 KB 命中与覆盖缺口两层）
  2. 每视频采集三信号原始值：
     - Pass-1 场景描述（VLM，落盘缓存跨实验复用）→ KB 词表命中关键词数
       + 场景描述负信号（"无明确文化符号"）
     - text 家族：KeywordCulturalRetriever 原始加权命中分 Top1/Top2
     - clip 家族（image/multimodal）：CLIP 融合分 Top1/Top2（alpha=0 / alpha=0.5）
  3. 网格搜索各模式族阈值（score_thr / margin_thr / require_keywords），
     目标函数 = 软平衡准确率：
       gap 样本（GT=unknown_symbol）：insufficient=1 / uncertain=0.5 / confident=0
       hit 样本（GT=真实符号）     ：confident=1   / uncertain=0.5 / insufficient=0
       score = (gap_mean + hit_mean) / 2，平分时优先 hit 放行率高
  4. 最优阈值写入 experiments/innovation2/data/eval/rejection_thresholds.json（含搜索报告与元信息）

用法：
    python scripts/innovation2/tune_rejection_thresholds.py \
        --gt experiments/innovation2/data/eval/cultural_ablation_gt_v2.jsonl --split val
"""

import os
import sys
import json
import time
import argparse
from itertools import product

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.pipeline.cultural_rag import SCENE_DESCRIBE_PROMPT
from src.pipeline.inference_engine import InferenceEngine
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.knowledge.retriever import KeywordCulturalRetriever, extract_cultural_query
from src.knowledge.multimodal_retriever import MultimodalCulturalRetriever
from src.experiments.ablation_metrics import load_gt
from src.knowledge.rejection_gate import (
    RejectionGate, LEVEL_CONFIDENT, LEVEL_UNCERTAIN, LEVEL_INSUFFICIENT,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_arguments():
    p = argparse.ArgumentParser(description="拒识阈值验证集网格搜索")
    p.add_argument("--gt", default="experiments/innovation2/data/eval/cultural_ablation_gt_v2.jsonl")
    p.add_argument("--split", default="val", choices=["val", "test"])
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--fusion-alpha", type=float, default=0.5)
    p.add_argument("--num-frames", type=int, default=4)
    p.add_argument("--scene-cache", default="experiments/innovation2/cache/scene_desc_cache_v2.json")
    p.add_argument("--output", default="experiments/innovation2/data/eval/rejection_thresholds.json")
    return p.parse_args()


# --------------------------------------------------------------------- #
# 信号采集
# --------------------------------------------------------------------- #
def collect_signals(gt_items, args):
    kb = SymbolKnowledgeBase()
    engine = InferenceEngine()
    engine.initialize()
    keyword_retriever = KeywordCulturalRetriever(kb)
    mm_retriever = MultimodalCulturalRetriever(
        kb=kb, fusion_alpha=args.fusion_alpha, num_frames=args.num_frames)

    cache_path = os.path.join(PROJECT_ROOT, args.scene_cache)
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        print(f"[场景缓存] 已加载 {len(cache)} 条")

    samples = []
    for i, gt in enumerate(gt_items, 1):
        video_abs = os.path.join(PROJECT_ROOT, gt["video_path"]) \
            if not os.path.isabs(gt["video_path"]) else gt["video_path"]
        if not os.path.exists(video_abs):
            print(f"[跳过] 视频不存在: {video_abs}")
            continue
        print(f"\n===== [{i}/{len(gt_items)}] {gt['video_id']} "
              f"(coverage={gt.get('kb_coverage')}) =====")

        scene = cache.get(gt["video_path"])
        if scene is None:
            t = time.time()
            scene = engine.annotate_video(video_abs, prompt=SCENE_DESCRIBE_PROMPT)
            cache[gt["video_path"]] = scene
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            print(f"  [Pass-1] {round(time.time() - t, 1)}s")
        else:
            print("  [Pass-1] 使用缓存")

        keywords = extract_cultural_query(kb, scene)
        n_kw = len(keywords)
        scene_neg = "无明确文化符号" in str(scene)
        ctx = {"video_path": video_abs, "scene_text": scene, "keywords": keywords}

        # text 家族：原始加权命中分
        text_cands = keyword_retriever.retrieve(ctx, top_k=args.top_k)
        text_scores = sorted((c.score for c in text_cands), reverse=True)

        # image 家族：alpha=0 → fusion = image 分数
        mm_retriever.fusion_alpha = 0.0
        img_cands = mm_retriever.retrieve(ctx, top_k=args.top_k)
        img_scores = sorted((c.fusion_score for c in img_cands), reverse=True)

        # multimodal 家族：alpha 融合
        mm_retriever.fusion_alpha = args.fusion_alpha
        mm_cands = mm_retriever.retrieve(ctx, top_k=args.top_k)
        mm_scores = sorted((c.fusion_score for c in mm_cands), reverse=True)

        def top2(scores):
            t1 = scores[0] if scores else 0.0
            t2 = scores[1] if len(scores) > 1 else 0.0
            return round(t1, 4), round(t2, 4)

        s = {
            "video_id": gt["video_id"], "kb_coverage": gt.get("kb_coverage", ""),
            "n_keywords": n_kw, "keywords": keywords, "scene_negative": scene_neg,
            "text": top2(text_scores), "image": top2(img_scores),
            "multimodal": top2(mm_scores),
        }
        print(f"  信号: n_kw={n_kw} scene_neg={scene_neg} "
              f"text={s['text']} image={s['image']} mm={s['multimodal']}")
        samples.append(s)
    return samples


# --------------------------------------------------------------------- #
# 网格搜索
# --------------------------------------------------------------------- #
def soft_score(level: str, is_gap: bool) -> float:
    if is_gap:
        return {LEVEL_INSUFFICIENT: 1.0, LEVEL_UNCERTAIN: 0.5, LEVEL_CONFIDENT: 0.0}[level]
    return {LEVEL_CONFIDENT: 1.0, LEVEL_UNCERTAIN: 0.5, LEVEL_INSUFFICIENT: 0.0}[level]


def evaluate(samples, family, thr) -> dict:
    gate = evaluate._gate
    gate.thresholds[family] = thr
    gap_scores, hit_scores, details = [], [], []
    for s in samples:
        t1, t2 = s[family]
        level = gate.decide_from_signals(
            t1, t2, s["n_keywords"], s["scene_negative"], family).level
        sc = soft_score(level, s["kb_coverage"] == "gap")
        (gap_scores if s["kb_coverage"] == "gap" else hit_scores).append(sc)
        details.append({"video_id": s["video_id"], "level": level, "score": sc})
    gap_mean = sum(gap_scores) / len(gap_scores) if gap_scores else 0.0
    hit_mean = sum(hit_scores) / len(hit_scores) if hit_scores else 0.0
    return {"balanced_acc": round((gap_mean + hit_mean) / 2, 4),
            "gap_reject": round(gap_mean, 4), "hit_pass": round(hit_mean, 4),
            "details": details}


def grid_search(samples, family, score_grid, margin_grid, require_kw_grid):
    best, best_key = None, None
    for s_thr, m_thr, req in product(score_grid, margin_grid, require_kw_grid):
        thr = {"signal": "text" if family == "text" else "fusion",
               "score_thr": round(s_thr, 4), "margin_thr": round(m_thr, 4),
               "require_keywords": req}
        r = evaluate(samples, family, thr)
        key = (r["balanced_acc"], r["hit_pass"], -m_thr)  # 平分优先放行hit，其次宽松分差
        if best_key is None or key > best_key:
            best_key, best = key, (thr, r)
    return best


def main():
    args = parse_arguments()
    gt_path = os.path.join(PROJECT_ROOT, args.gt) \
        if not os.path.isabs(args.gt) else args.gt
    items = [g for g in load_gt(gt_path) if g.get("split", "test") == args.split]
    n_gap = sum(1 for g in items if g.get("kb_coverage") == "gap")
    n_hit = len(items) - n_gap
    print(f"[验证集] {len(items)} 样本（gap={n_gap}, hit={n_hit}）")

    # 复用同一 RejectionGate 实例做决策（仅借其判定逻辑，阈值逐组覆盖）
    evaluate._gate = RejectionGate.__new__(RejectionGate)
    evaluate._gate.config = {}
    evaluate._gate.thresholds = {}

    samples = collect_signals(items, args)
    sig_path = os.path.join(PROJECT_ROOT, 'experiments/innovation2/cache/rejection_val_signals.json')
    with open(sig_path, "w", encoding="utf-8") as f:
        json.dump({"gt": args.gt, "split": args.split, "samples": samples},
                  f, ensure_ascii=False, indent=2)
    print(f"\n[信号落盘] {sig_path}")

    # ---- text 家族：原始加权命中分（规范名/别名+3，特征词+1） ----
    text_scores_all = sorted({v for s in samples for v in s["text"]})
    text_grid = sorted(set(
        [0.5] + [round(x - 0.5, 2) for x in text_scores_all if x > 0.5]
        + [round(x, 2) for x in text_scores_all if x > 0]))
    text_best = grid_search(samples, "text", text_grid,
                            [0, 0.05, 0.1, 0.15, 0.2, 0.3], [True])

    # ---- clip 家族（image/multimodal）：归一化融合分 ----
    clip_score_grid = [round(0.40 + 0.005 * i, 4) for i in range(41)]  # 0.40~0.60
    clip_margin_grid = [0, 0.002, 0.005, 0.01, 0.02, 0.03, 0.05]
    image_best = grid_search(samples, "image", clip_score_grid,
                             clip_margin_grid, [True, False])
    mm_best = grid_search(samples, "multimodal", clip_score_grid,
                          clip_margin_grid, [True, False])

    thresholds, report = {}, {}
    for family, (thr, r) in [("text", text_best), ("image", image_best),
                             ("multimodal", mm_best)]:
        thresholds[family] = thr
        report[family] = {k: v for k, v in r.items() if k != "details"}
        print(f"\n[{family}] thr={thr} → balanced_acc={r['balanced_acc']} "
              f"gap_reject={r['gap_reject']} hit_pass={r['hit_pass']}")
        for d in r["details"]:
            mark = "✓" if d["score"] >= 1 else ("~" if d["score"] > 0 else "✗")
            print(f"    {mark} {d['video_id']}: {d['level']}")

    out_path = os.path.join(PROJECT_ROOT, args.output) \
        if not os.path.isabs(args.output) else args.output
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "version": "v2-30sucai",
            "tuned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "val_gt": args.gt, "val_split": args.split,
            "val_size": len(samples), "n_gap": n_gap, "n_hit": n_hit,
            "objective": "soft balanced acc: gap(insufficient=1/uncertain=0.5/confident=0) "
                         "vs hit(confident=1/uncertain=0.5/insufficient=0)",
            "signal_file": os.path.relpath(sig_path, PROJECT_ROOT),
            "thresholds": thresholds,
            "report": report,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n[阈值落盘] {out_path}")


if __name__ == "__main__":
    main()
