"""
创新点2 消融实验 CLI 入口（5 种模式端到端跑通）

用法：
    # 默认：GT 全部视频 × 全部 5 种模式
    python scripts/innovation2/run_cultural_ablation.py

    # 仅指定模式与视频
    python scripts/innovation2/run_cultural_ablation.py --modes free,multimodal --video-ids niaochao

    # 自定义候选数与融合权重
    python scripts/innovation2/run_cultural_ablation.py --top-k 5 --fusion-alpha 0.5

输出（experiments/innovation2/runs/cultural_ablation/<时间戳>/）：
    results.json / per_video.csv / summary.csv + 每视频每模式中间产物
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.experiments import CulturalAblationExperiment, ALL_MODES


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="创新点2 消融实验：Free/Text/Image/Multimodal/Controlled 五模式对比"
    )
    parser.add_argument("--gt", default="experiments/innovation2/data/eval/cultural_ablation_gt.jsonl",
                        help="GT 评测集路径（默认 experiments/innovation2/data/eval/cultural_ablation_gt.jsonl）")
    parser.add_argument("--modes", default=",".join(ALL_MODES),
                        help="逗号分隔的实验模式（默认全部5种）")
    parser.add_argument("--video-ids", default=None,
                        help="逗号分隔的 video_id（默认 GT 全部）")
    parser.add_argument("--split", default=None, choices=["val", "test"],
                        help="仅跑指定划分（GT v2 支持 val/test，默认全部）")
    parser.add_argument("--top-k", type=int, default=5, help="检索候选数（默认5）")
    parser.add_argument("--fusion-alpha", type=float, default=0.5,
                        help="融合中文本权重（0~1），默认0.5")
    parser.add_argument("--num-frames", type=int, default=4,
                        help="CLIP 视频关键帧采样数（默认4）")
    parser.add_argument("--no-gate", action="store_true",
                        help="关闭拒识门控（默认开启，若阈值配置存在）")
    parser.add_argument("--thresholds", default="experiments/innovation2/data/eval/rejection_thresholds.json",
                        help="拒识阈值配置路径（验证集搜索产出）")
    parser.add_argument("--identity-gate", action="store_true",
                        help="在拒识门控之上叠加 Identity Evidence Gate（实验二 Proposed）")
    parser.add_argument("--scene-cache", default="experiments/innovation2/cache/scene_desc_cache_v2.json",
                        help="Pass-1 场景描述缓存 JSON 路径（跨实验复用）")
    parser.add_argument("--output-dir", "-o", default=None, help="实验输出目录")
    return parser.parse_args()


def main():
    args = parse_arguments()
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    video_ids = [v.strip() for v in args.video_ids.split(",")] if args.video_ids else None

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    gt_path = os.path.join(project_root, args.gt) if not os.path.isabs(args.gt) else args.gt
    thresholds_path = os.path.join(project_root, args.thresholds) \
        if not os.path.isabs(args.thresholds) else args.thresholds
    scene_cache_path = os.path.join(project_root, args.scene_cache) \
        if not os.path.isabs(args.scene_cache) else args.scene_cache

    use_gate = (not args.no_gate) and os.path.exists(thresholds_path)
    if (not args.no_gate) and not os.path.exists(thresholds_path):
        print(f"[提示] 阈值配置不存在（{thresholds_path}），拒识门控自动关闭（旧行为）")

    exp = CulturalAblationExperiment(
        gt_path=gt_path, top_k=args.top_k,
        fusion_alpha=args.fusion_alpha, num_frames=args.num_frames,
        use_rejection_gate=use_gate, thresholds_path=thresholds_path,
        scene_cache_path=scene_cache_path,
        use_identity_gate=args.identity_gate)

    result = exp.run(modes=modes, video_ids=video_ids, out_dir=args.output_dir,
                     split=args.split)

    print("\n===== 消融实验汇总 =====")
    print(json.dumps(result["summaries"], ensure_ascii=False, indent=2))
    print(f"\n详细结果: {result['exp_dir']}")


if __name__ == "__main__":
    main()
