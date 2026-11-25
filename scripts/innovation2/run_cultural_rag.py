"""
创新点2 端到端文化检索链路 - 运行脚本

链路：视频关键帧 → VLM视觉描述 → 提取文化Query → KeywordCulturalRetriever
      → Top-K文化候选 → 动态注入Prompt → EMCAST C层文化标注

用法示例：
    # KB 检索链路（默认，Top-5 候选）
    python scripts/innovation2/run_cultural_rag.py --video data/test/鸟巢.mp4

    # KB + Free Prompt 双模式对照
    python scripts/innovation2/run_cultural_rag.py --video data/test/鸟巢.mp4 --mode both

    # Free Prompt 模式（无知识库）
    python scripts/innovation2/run_cultural_rag.py --video data/test/鸟巢.mp4 --mode free

    # 指定候选数
    python scripts/innovation2/run_cultural_rag.py --video data/test/鸟巢.mp4 --top-k 3

中间结果（视觉描述/Query/Top-K候选及分数/Prompt/最终C层结果）落盘于
experiments/innovation2/outputs/cultural_rag/<时间戳>_<视频名>/，汇总见 pipeline_trace.json。
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.pipeline.cultural_rag import CulturalRAGPipeline


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="创新点2：中华文化知识库检索驱动的 EMCAST 受控标注链路"
    )
    parser.add_argument("--video", "-v", required=True, help="视频文件路径")
    parser.add_argument("--mode", choices=["kb", "free", "both"], default="kb",
                        help="kb=知识库检索链路；free=无知识库Free Prompt；both=双模式对照")
    parser.add_argument("--retriever", choices=["keyword", "multimodal"], default="keyword",
                        help="检索器：keyword=关键词检索；multimodal=CLIP图像+文本融合检索（仅kb模式生效）")
    parser.add_argument("--top-k", type=int, default=5, help="检索候选数（默认5）")
    parser.add_argument("--fusion-alpha", type=float, default=0.5,
                        help="融合中文本分数权重（0~1），图像权重=1-alpha，默认0.5")
    parser.add_argument("--num-frames", type=int, default=4,
                        help="多模态检索视频关键帧采样数（默认4）")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="输出目录（默认 experiments/innovation2/outputs/cultural_rag/<时间戳>_<视频名>）")
    parser.add_argument("--retrieval-strategy", choices=["legacy", "evidence_v1"], default="legacy")
    return parser.parse_args()


def print_trace(trace):
    print(f"\n{'=' * 60}")
    print(f"[模式] {trace['mode']}  [检索器] {trace.get('retriever')}  "
          f"[耗时] {trace['total_seconds']}s  [步骤耗时] {trace['steps']}")
    if trace.get("scene_description"):
        print(f"\n--- Step1 VLM 视觉描述 ---\n{trace['scene_description']}")
    if trace.get("cultural_query"):
        print(f"\n--- Step2 文化 Query ---\n关键词: {trace['cultural_query']['keywords']}")
    if trace.get("topk_candidates") is not None:
        print(f"\n--- Step3 Top-{trace.get('top_k')} 候选 ---")
        for c in trace["topk_candidates"]:
            line = (f"  {c['symbol_id']}  {c['canonical_name']}  "
                    f"[{c['dimension_code']}]  fusion={c.get('fusion_score', c['score']):.4f}"
                    f"  (text={c.get('text_score', 0):.4f}  image={c.get('image_score', 0):.4f})"
                    f"  {c['reason']}")
            print(line)
    c = trace.get("final_c_layer", {})
    print(f"\n--- 最终 C 层结果 ---")
    print(f"  维度: {c.get('dimension') or '(未解析)'}")
    print(f"  核心符号: {c.get('core_symbol') or '(未解析)'}")
    print(f"  unknown_symbol: {c.get('unknown_symbol')}")
    print(f"{'=' * 60}\n")


def main():
    args = parse_arguments()
    if not os.path.exists(args.video):
        print(f"错误: 视频不存在: {args.video}")
        sys.exit(1)

    # 按需构造检索器
    retriever = None
    if args.retriever != "multimodal" and args.retrieval_strategy != "legacy":
        raise ValueError("evidence_v1 requires --retriever multimodal")
    if args.retriever == "multimodal":
        from src.knowledge import MultimodalCulturalRetriever
        retriever = MultimodalCulturalRetriever(
            ranking_strategy=args.retrieval_strategy,
            fusion_alpha=args.fusion_alpha,
            num_frames=args.num_frames,
        )
        print(f"--- 使用多模态检索器: fusion_alpha={args.fusion_alpha}, "
              f"num_frames={args.num_frames} ---")
    else:
        from src.knowledge import KeywordCulturalRetriever, SymbolKnowledgeBase
        retriever = KeywordCulturalRetriever(SymbolKnowledgeBase())
        print("--- 使用关键词检索器 ---")

    pipeline = CulturalRAGPipeline(retriever=retriever, top_k=args.top_k)
    modes = ["kb", "free"] if args.mode == "both" else [args.mode]

    traces = []
    out_dir = args.output_dir
    for mode in modes:
        trace = pipeline.run(args.video, use_kb=(mode == "kb"), out_dir=out_dir)
        out_dir = trace["output_dir"]  # both 模式复用同一目录
        print_trace(trace)
        traces.append(trace)

    trace_path = pipeline.save_trace(traces, out_dir)
    print(f"全部中间结果与 trace 已保存到: {out_dir}")
    print(f"汇总 trace: {trace_path}")


if __name__ == "__main__":
    main()
