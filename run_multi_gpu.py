"""
多GPU并行运行脚本
根据GPU占用情况智能分配任务到多个GPU
"""

import os
import sys
import argparse
import subprocess
import time
from typing import List, Dict, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp

# 直接导入gpu_manager，避免导入整个src包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from gpu_manager import GPUManager


def run_single_gpu_task(gpu_id: int, video_path: str, 
                       output_dir: str, model_path: Optional[str] = None,
                       fps: Optional[float] = None, max_frames: Optional[int] = None,
                       output_format: str = "both", format_type: str = "standard",
                       verbose: bool = False) -> Dict[str, any]:
    """
    在单个GPU上运行视频标注任务
    
    Args:
        gpu_id: GPU ID
        video_path: 视频文件路径
        output_dir: 输出目录
        model_path: 模型路径
        fps: 视频采样帧率
        max_frames: 最大帧数限制
        output_format: 输出格式
        format_type: 标注内容格式类型
        verbose: 是否显示详细信息
    
    Returns:
        任务结果字典
    """
    result = {
        "gpu_id": gpu_id,
        "video_path": video_path,
        "success": False,
        "error": None,
        "output_files": []
    }
    
    try:
        # 构建命令
        cmd = [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "src", "run_cultural_annotation.py"),
            "--video", video_path,
            "--gpu", str(gpu_id),
            "--output-dir", output_dir,
            "--output-format", output_format,
            "--format-type", format_type
        ]
        
        if model_path:
            cmd.extend(["--model-path", model_path])
        
        if fps:
            cmd.extend(["--fps", str(fps)])
        
        if max_frames:
            cmd.extend(["--max-frames", str(max_frames)])
        
        if verbose:
            cmd.append("--verbose")
        
        # 设置环境变量
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
        
        # 执行命令
        if verbose:
            print(f"[GPU {gpu_id}] 开始处理: {os.path.basename(video_path)}")
        
        process = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=3600  # 1小时超时
        )
        
        if process.returncode == 0:
            result["success"] = True
            if verbose:
                print(f"[GPU {gpu_id}] 完成: {os.path.basename(video_path)}")
        else:
            result["error"] = process.stderr
            if verbose:
                print(f"[GPU {gpu_id}] 失败: {os.path.basename(video_path)}")
                print(f"  错误: {result['error']}")
    
    except subprocess.TimeoutExpired:
        result["error"] = "任务超时（1小时）"
        if verbose:
            print(f"[GPU {gpu_id}] 超时: {os.path.basename(video_path)}")
    
    except Exception as e:
        result["error"] = str(e)
        if verbose:
            print(f"[GPU {gpu_id}] 异常: {os.path.basename(video_path)}")
            print(f"  异常: {result['error']}")
    
    return result


def distribute_videos_to_gpus(video_paths: List[str], gpu_manager: GPUManager, 
                             videos_per_gpu: int = 1) -> Dict[int, List[str]]:
    """
    将视频分配到GPU
    
    Args:
        video_paths: 视频文件路径列表
        gpu_manager: GPU管理器
        videos_per_gpu: 每个GPU处理的视频数量
    
    Returns:
        GPU ID到视频列表的映射
    """
    # 获取可用GPU
    available_gpus = gpu_manager.get_available_gpus(min_memory_mb=10000)
    
    if not available_gpus:
        print("错误: 没有可用的GPU")
        return {}
    
    # 计算需要的GPU数量
    num_videos = len(video_paths)
    num_gpus_needed = min(len(available_gpus), (num_videos + videos_per_gpu - 1) // videos_per_gpu)
    
    selected_gpus = available_gpus[:num_gpus_needed]
    
    # 分配视频到GPU
    gpu_video_map = {}
    for i, gpu in enumerate(selected_gpus):
        start_idx = i * videos_per_gpu
        end_idx = min(start_idx + videos_per_gpu, num_videos)
        
        if start_idx < num_videos:
            gpu_video_map[gpu.gpu_id] = video_paths[start_idx:end_idx]
    
    return gpu_video_map


def run_parallel_tasks(tasks: List[tuple], max_workers: Optional[int] = None) -> List[Dict]:
    """
    并行运行任务
    
    Args:
        tasks: 任务列表，每个任务是一个元组 (gpu_id, video_path, ...)
        max_workers: 最大工作进程数
    
    Returns:
        任务结果列表
    """
    if max_workers is None:
        max_workers = len(tasks)
    
    results = []
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_task = {
            executor.submit(run_single_gpu_task, *task): task 
            for task in tasks
        }
        
        # 收集结果
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                gpu_id, video_path = task[0], task[1]
                results.append({
                    "gpu_id": gpu_id,
                    "video_path": video_path,
                    "success": False,
                    "error": str(e)
                })
    
    return results


def print_summary(results: List[Dict]):
    """
    打印任务执行摘要
    
    Args:
        results: 任务结果列表
    """
    total = len(results)
    success = sum(1 for r in results if r["success"])
    failed = total - success
    
    print("\n" + "="*80)
    print("任务执行摘要")
    print("="*80)
    print(f"总计: {total}")
    print(f"成功: {success}")
    print(f"失败: {failed}")
    
    if failed > 0:
        print("\n失败任务:")
        for result in results:
            if not result["success"]:
                print(f"  GPU {result['gpu_id']}: {os.path.basename(result['video_path'])}")
                print(f"    错误: {result['error']}")
    
    print("="*80)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="多GPU并行视频标注系统"
    )
    
    parser.add_argument(
        "--video", "-v",
        type=str,
        nargs='+',
        help="视频文件路径（可指定多个）"
    )
    
    parser.add_argument(
        "--video-dir", "-d",
        type=str,
        help="视频目录路径"
    )
    
    parser.add_argument(
        "--gpu-ids",
        type=int,
        nargs='+',
        default=[0, 1, 2, 3, 4],
        help="要使用的GPU ID列表，默认为0-4"
    )
    
    parser.add_argument(
        "--videos-per-gpu",
        type=int,
        default=1,
        help="每个GPU处理的视频数量，默认为1"
    )
    
    parser.add_argument(
        "--model-path", "-m",
        type=str,
        default=None,
        help="模型路径"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=None,
        help="输出目录"
    )
    
    parser.add_argument(
        "--fps", "-f",
        type=float,
        default=None,
        help="视频采样帧率"
    )
    
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="最大帧数限制"
    )
    
    parser.add_argument(
        "--output-format",
        type=str,
        choices=["txt", "json", "both"],
        default="both",
        help="输出格式"
    )
    
    parser.add_argument(
        "--format-type", "-t",
        type=str,
        choices=["clean", "standard", "detailed"],
        default="standard",
        help="标注内容格式类型"
    )
    
    parser.add_argument(
        "--verbose", "-V",
        action="store_true",
        help="显示详细信息"
    )
    
    parser.add_argument(
        "--check-gpu-only",
        action="store_true",
        help="仅检查GPU状态，不执行任务"
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


def main():
    """主函数"""
    args = parse_arguments()
    
    # 创建GPU管理器
    gpu_manager = GPUManager(gpu_ids=args.gpu_ids)
    
    # 打印GPU状态
    gpu_manager.print_gpu_status()
    
    # 如果仅检查GPU状态，则退出
    if args.check_gpu_only:
        return
    
    # 获取视频文件列表
    video_paths = []
    
    if args.video:
        video_paths.extend(args.video)
    
    if args.video_dir:
        video_paths.extend(get_video_files(args.video_dir))
    
    if not video_paths:
        print("错误: 未指定视频文件或视频目录")
        sys.exit(1)
    
    print(f"\n找到 {len(video_paths)} 个视频文件")
    
    # 设置输出目录
    if args.output_dir is None:
        args.output_dir = os.path.join(os.path.dirname(__file__), "outputs")
    
    # 分配视频到GPU
    gpu_video_map = distribute_videos_to_gpus(
        video_paths, gpu_manager, args.videos_per_gpu
    )
    
    if not gpu_video_map:
        print("错误: 无法分配视频到GPU")
        sys.exit(1)
    
    print(f"\n任务分配:")
    for gpu_id, videos in gpu_video_map.items():
        print(f"  GPU {gpu_id}: {len(videos)} 个视频")
        for video in videos:
            print(f"    - {os.path.basename(video)}")
    
    # 构建任务列表
    tasks = []
    for gpu_id, videos in gpu_video_map.items():
        for video_path in videos:
            tasks.append((
                gpu_id, video_path, args.output_dir, args.model_path,
                args.fps, args.max_frames, args.output_format, 
                args.format_type, args.verbose
            ))
    
    print(f"\n开始并行处理 {len(tasks)} 个任务...")
    print("="*80)
    
    # 并行运行任务
    start_time = time.time()
    results = run_parallel_tasks(tasks, max_workers=len(gpu_video_map))
    end_time = time.time()
    
    # 打印摘要
    print_summary(results)
    
    print(f"\n总耗时: {end_time - start_time:.2f} 秒")
    
    # 检查是否所有任务都成功
    all_success = all(r["success"] for r in results)
    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    main()
