"""
文化视频标注系统 - 主程序
使用模块化架构的视频标注工具
"""

import os
import sys
import argparse
import time
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["CUDA_VISIBLE_DEVICES"] = "5"

from src.config import Config
from src.inference_engine import InferenceEngine
from src.result_processor import ResultProcessor
from src.video_processor import VideoProcessor


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="北京文化视频标注系统 - EMCAST六维分层标注"
    )
    
    parser.add_argument(
        "--video", "-v",
        type=str,
        help="视频文件路径"
    )
    
    parser.add_argument(
        "--video-dir", "-d",
        type=str,
        help="视频目录路径（批量处理）"
    )
    
    parser.add_argument(
        "--model-path", "-m",
        type=str,
        default=None,
        help="模型路径，默认使用配置文件中的路径"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=None,
        help="输出目录，默认使用配置文件中的路径"
    )
    
    parser.add_argument(
        "--fps", "-f",
        type=float,
        default=None,
        help="视频采样帧率，默认使用配置文件中的值"
    )
    
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="最大帧数限制"
    )
    
    parser.add_argument(
        "--gpu",
        type=int,
        default=None,
        help="GPU设备ID，默认使用配置文件中的值"
    )
    
    parser.add_argument(
        "--output-format",
        type=str,
        choices=["txt", "json", "both"],
        default="both",
        help="输出格式，默认为both"
    )
    
    parser.add_argument(
        "--format-type", "-t",
        type=str,
        choices=["clean", "standard", "detailed"],
        default="standard",
        help="标注内容格式类型: clean(纯净EMCAST), standard(文件信息+EMCAST), detailed(完整含思考过程)，默认为standard"
    )
    
    parser.add_argument(
        "--no-ffmpeg",
        action="store_true",
        help="禁用ffmpeg元数据获取"
    )
    
    parser.add_argument(
        "--verbose", "-V",
        action="store_true",
        help="显示详细信息"
    )
    
    return parser.parse_args()


def get_video_files(directory: str) -> List[str]:
    """
    获取目录中的所有视频文件
    
    Args:
        directory: 目录路径
    
    Returns:
        视频文件路径列表
    """
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.webm'}
    video_files = []
    
    if not os.path.isdir(directory):
        print(f"错误: 目录不存在: {directory}")
        return video_files
    
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            ext = os.path.splitext(filename)[1].lower()
            if ext in video_extensions:
                video_files.append(filepath)
    
    return sorted(video_files)


def process_single_video(video_path: str, config: Config, 
                         inference_engine: InferenceEngine,
                         result_processor: ResultProcessor,
                         output_format: str = "both",
                         format_type: str = "standard",
                         verbose: bool = False) -> bool:
    """
    处理单个视频
    
    Args:
        video_path: 视频文件路径
        config: 配置对象
        inference_engine: 推理引擎
        result_processor: 结果处理器
        output_format: 输出格式
        format_type: 标注内容格式类型
        verbose: 是否显示详细信息
    
    Returns:
        是否处理成功
    """
    try:
        if verbose:
            print(f"\n{'='*60}")
            print(f"正在处理视频: {os.path.basename(video_path)}")
            print(f"{'='*60}")
            
            video_info = inference_engine.get_video_info(video_path)
            print(video_info)
            print(f"{'='*60}")
        
        print(f"--- 开始标注: {os.path.basename(video_path)} ---")
        
        # 开始计时
        start_time = time.time()
        
        annotation_text = inference_engine.annotate_video(video_path)
        
        # 结束计时并计算处理时间
        end_time = time.time()
        processing_time_seconds = end_time - start_time
        # 格式化处理时间为分:秒格式
        processing_time = f"{int(processing_time_seconds // 60)}分{int(processing_time_seconds % 60)}秒"
        
        if verbose:
            print(f"--- 标注完成 ---")
            print(f"处理时间: {processing_time}")
        
        video_metadata = inference_engine.video_processor.get_video_metadata(video_path)
        result = result_processor.create_result(
            video_path=video_path,
            annotation_text=annotation_text,
            metadata=video_metadata.to_dict(),
            processing_time=processing_time
        )
        
        result_processor.print_result(result, format_type)
        
        saved_files = result_processor.save_result(result, output_format, format_type=format_type)
        print(f"\n结果已保存到: {saved_files}")
        
        return True
        
    except Exception as e:
        print(f"处理视频失败 {video_path}: {str(e)}")
        return False


def process_batch_videos(video_paths: List[str], config: Config,
                        inference_engine: InferenceEngine,
                        result_processor: ResultProcessor,
                        output_format: str = "both",
                        format_type: str = "standard",
                        verbose: bool = False) -> dict:
    """
    批量处理视频
    
    Args:
        video_paths: 视频文件路径列表
        config: 配置对象
        inference_engine: 推理引擎
        result_processor: 结果处理器
        output_format: 输出格式
        format_type: 标注内容格式类型
        verbose: 是否显示详细信息
    
    Returns:
        处理结果统计字典
    """
    results = {
        "total": len(video_paths),
        "success": 0,
        "failed": 0,
        "failed_files": []
    }
    
    print(f"\n开始批量处理 {len(video_paths)} 个视频文件")
    print(f"{'='*60}")
    
    for i, video_path in enumerate(video_paths, 1):
        print(f"\n[{i}/{len(video_paths)}] ", end="")
        
        success = process_single_video(
            video_path, config, inference_engine, 
            result_processor, output_format, format_type, verbose
        )
        
        if success:
            results["success"] += 1
        else:
            results["failed"] += 1
            results["failed_files"].append(video_path)
    
    print(f"\n{'='*60}")
    print(f"批量处理完成:")
    print(f"  总计: {results['total']}")
    print(f"  成功: {results['success']}")
    print(f"  失败: {results['failed']}")
    
    if results["failed_files"]:
        print(f"\n失败文件:")
        for failed_file in results["failed_files"]:
            print(f"  - {failed_file}")
    
    return results


def main():
    """主函数"""
    args = parse_arguments()
    
    if not args.video and not args.video_dir:
        print("错误: 请指定视频文件或视频目录")
        print("使用 --help 查看帮助信息")
        sys.exit(1)
    
    if args.video and args.video_dir:
        print("警告: 同时指定了视频文件和视频目录，将只处理单个视频文件")
    
    config = Config()
    
    if args.model_path:
        config.model.model_path = args.model_path
    
    if args.output_dir:
        config.paths.output_dir = args.output_dir
    
    if args.fps:
        config.video.fps = args.fps
    
    if args.gpu:
        config.gpu.device_id = args.gpu
        config.gpu.visible_devices = str(args.gpu)
        config.model.device_map = {"": 0}  # 设置CUDA_VISIBLE_DEVICES后，GPU 5变成GPU 0
        os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
    
    if args.no_ffmpeg:
        config.video.use_ffmpeg_metadata = False
    
    inference_engine = InferenceEngine(config)
    result_processor = ResultProcessor(config.paths.output_dir)
    
    try:
        inference_engine.initialize()
        
        if args.video:
            success = process_single_video(
                args.video, config, inference_engine, 
                result_processor, args.output_format, args.format_type, args.verbose
            )
            sys.exit(0 if success else 1)
        
        elif args.video_dir:
            video_paths = get_video_files(args.video_dir)
            
            if not video_paths:
                print(f"错误: 在目录中未找到视频文件: {args.video_dir}")
                sys.exit(1)
            
            results = process_batch_videos(
                video_paths, config, inference_engine,
                result_processor, args.output_format, args.format_type, args.verbose
            )
            
            sys.exit(0 if results["failed"] == 0 else 1)
    
    except KeyboardInterrupt:
        print("\n\n用户中断程序")
        inference_engine.cleanup()
        sys.exit(130)
    
    except Exception as e:
        print(f"\n程序执行出错: {str(e)}")
        import traceback
        traceback.print_exc()
        inference_engine.cleanup()
        sys.exit(1)
    
    finally:
        inference_engine.cleanup()


if __name__ == "__main__":
    main()