"""
带学习功能的视频标注程序
集成 RAG + Few-shot 学习系统，不破坏原有程序
"""

import os
import sys
import argparse
import json
from datetime import datetime

# 添加项目根目录到路径，使 src 作为包被识别
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.models.config import Config
from src.pipeline.inference_engine import InferenceEngine
from src.pipeline.result_processor import ResultProcessor
from src.pipeline.video_processor import VideoProcessor
from src.pipeline.prompt_manager import PromptManager

# 导入学习模块
from src.learning.config import LearningConfig
from src.learning.run_learning import LearningPipeline


def annotate_with_learning(
    video_path: str,
    output_dir: str = None,
    learning_config: LearningConfig = None,
    enable_learning: bool = True,
    correction_reason: str = None,
    annotator: str = None
):
    """
    使用学习功能进行视频标注
    
    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
        learning_config: 学习配置
        enable_learning: 是否启用学习功能
        correction_reason: 修改原因（用于学习）
        annotator: 标注员
    """
    # 初始化配置
    config = Config()
    if output_dir:
        config.paths.output_dir = output_dir
    
    # 初始化学习系统
    if enable_learning:
        learning_config = learning_config or LearningConfig(enabled=True)
        learning_pipeline = LearningPipeline(learning_config)
    else:
        learning_pipeline = None
    
    # 初始化推理引擎
    engine = InferenceEngine(config)
    
    # 获取视频元数据
    video_processor = VideoProcessor()
    video_metadata = video_processor.get_video_metadata(video_path)
    
    # 检测场景分类
    prompt_manager = PromptManager()
    scene_info = prompt_manager._detect_scene_from_path(video_path)
    scene_category = scene_info.get('category', '')
    
    # 获取基础提示词
    base_prompt = prompt_manager.get_emcast_prompt(
        video_metadata.to_dict(),
        video_path=video_path
    )
    
    # 如果启用学习，增强提示词
    if enable_learning and learning_pipeline:
        print("\n" + "="*60)
        print("启用 RAG + Few-shot 学习模式")
        print("="*60)
        
        # 构建视频描述用于检索
        video_description = f"{scene_category} {os.path.basename(video_path)}"
        
        # 获取增强后的提示词
        enhanced_prompt = learning_pipeline.get_enhanced_prompt(
            base_prompt=base_prompt,
            scene_category=scene_category,
            video_description=video_description
        )
        
        prompt = enhanced_prompt
    else:
        prompt = base_prompt
    
    # 执行标注
    print(f"\n开始标注视频: {video_path}")
    result = engine.annotate_video(video_path, prompt=prompt)
    
    # 处理结果
    processor = ResultProcessor(config.paths.output_dir)
    output_files = processor.save_result(
        result=result,
        video_path=video_path,
        video_metadata=video_metadata.to_dict()
    )
    
    print(f"\n标注完成，结果已保存:")
    for file_path in output_files:
        print(f"  - {file_path}")
    
    return result, output_files


def interactive_correction(
    video_path: str,
    original_result: str,
    output_files: list,
    learning_pipeline: LearningPipeline,
    annotator: str = None
):
    """
    交互式修正流程
    
    Args:
        video_path: 视频路径
        original_result: 原始标注结果
        output_files: 输出文件列表
        learning_pipeline: 学习流程实例
        annotator: 标注员
    """
    print("\n" + "="*60)
    print("交互式修正模式")
    print("="*60)
    
    print("\n原始标注结果:")
    print("-"*40)
    print(original_result[:500] + "..." if len(original_result) > 500 else original_result)
    print("-"*40)
    
    # 提示用户输入修正内容
    print("\n请输入修正后的标注内容（输入 'skip' 跳过，输入 'done' 结束）:")
    
    # 读取修正内容
    corrected_lines = []
    print("开始输入修正内容（每行一条，空行结束）:")
    
    while True:
        try:
            line = input()
            if line.strip() == '':
                break
            corrected_lines.append(line)
        except EOFError:
            break
    
    if not corrected_lines:
        print("未输入修正内容，跳过学习")
        return
    
    corrected_annotation = '\n'.join(corrected_lines)
    
    # 输入修改原因
    print("\n请输入修改原因（可选，直接回车跳过）:")
    try:
        correction_reason = input().strip()
    except EOFError:
        correction_reason = None
    
    # 收集并学习
    if corrected_annotation != original_result:
        case = learning_pipeline.collect_and_learn(
            video_path=video_path,
            original_annotation=original_result,
            corrected_annotation=corrected_annotation,
            correction_reason=correction_reason,
            annotator=annotator
        )
        
        # 更新输出文件
        for output_file in output_files:
            if output_file.endswith('.txt'):
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(corrected_annotation)
                print(f"已更新标注文件: {output_file}")
        
        print("\n修正内容已学习，下次标注将参考此修正案例")
    else:
        print("\n修正内容与原始标注相同，无需学习")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='带学习功能的视频标注程序',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基础标注（启用学习）
  python run_with_learning.py --video data/test.mp4
  
  # 标注并进入交互式修正模式
  python run_with_learning.py --video data/test.mp4 --interactive
  
  # 禁用学习功能
  python run_with_learning.py --video data/test.mp4 --no-learning
  
  # 从修正文件学习
  python run_with_learning.py --video data/test.mp4 --learn-from correction.json
        """
    )
    
    parser.add_argument('--video', required=True, help='视频文件路径')
    parser.add_argument('--output', help='输出目录')
    parser.add_argument('--annotator', help='标注员标识')
    
    # 学习功能选项
    parser.add_argument('--no-learning', action='store_true', help='禁用学习功能')
    parser.add_argument('--interactive', action='store_true', help='进入交互式修正模式')
    parser.add_argument('--learn-from', help='从修正文件学习（JSON格式）')
    
    # Few-shot 配置
    parser.add_argument('--max-examples', type=int, default=3, help='Few-shot 示例数量')
    parser.add_argument('--min-similarity', type=float, default=0.6, help='最小相似度阈值')
    
    args = parser.parse_args()
    
    # 配置学习参数
    learning_config = LearningConfig(
        enabled=not args.no_learning,
        max_examples_per_query=args.max_examples,
        min_similarity_score=args.min_similarity
    )
    
    # 执行标注
    result, output_files = annotate_with_learning(
        video_path=args.video,
        output_dir=args.output,
        learning_config=learning_config,
        enable_learning=not args.no_learning,
        annotator=args.annotator
    )
    
    # 如果指定了从修正文件学习
    if args.learn_from:
        learning_pipeline = LearningPipeline(learning_config)
        
        with open(args.learn_from, 'r', encoding='utf-8') as f:
            correction_data = json.load(f)
        
        learning_pipeline.collect_and_learn(
            video_path=args.video,
            original_annotation=correction_data.get('original', result),
            corrected_annotation=correction_data.get('corrected', ''),
            correction_reason=correction_data.get('reason'),
            annotator=args.annotator
        )
    
    # 如果进入交互式修正模式
    elif args.interactive and not args.no_learning:
        learning_pipeline = LearningPipeline(learning_config)
        interactive_correction(
            video_path=args.video,
            original_result=result,
            output_files=output_files,
            learning_pipeline=learning_pipeline,
            annotator=args.annotator
        )


if __name__ == '__main__':
    main()