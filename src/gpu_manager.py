"""
GPU管理模块
负责检测GPU状态、分配任务和管理多GPU并行处理
"""

import os
import subprocess
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import time


@dataclass
class GPUInfo:
    """GPU信息类"""
    gpu_id: int
    name: str
    memory_used: int  # MB
    memory_total: int  # MB
    memory_free: int  # MB
    utilization: int  # 百分比
    processes: int  # 进程数
    
    @property
    def memory_usage_percent(self) -> float:
        """内存使用百分比"""
        if self.memory_total == 0:
            return 0.0
        return (self.memory_used / self.memory_total) * 100
    
    @property
    def is_available(self) -> bool:
        """GPU是否可用（内存使用小于90%）"""
        return self.memory_usage_percent < 90.0
    
    @property
    def score(self) -> float:
        """GPU可用性评分（越高越适合分配任务）"""
        if not self.is_available:
            return -1.0
        
        # 综合考虑内存使用率和GPU利用率
        memory_score = 100 - self.memory_usage_percent
        utilization_score = 100 - self.utilization
        process_penalty = self.processes * 5  # 每个进程扣5分
        
        return memory_score * 0.5 + utilization_score * 0.4 - process_penalty


class GPUManager:
    """GPU管理器，负责检测和分配GPU资源"""
    
    def __init__(self, gpu_ids: Optional[List[int]] = None):
        """
        初始化GPU管理器
        
        Args:
            gpu_ids: 要监控的GPU ID列表，如果为None则监控所有可用GPU
        """
        self.gpu_ids = gpu_ids or list(range(8))  # 默认监控0-7号GPU
        self.gpu_info: Dict[int, GPUInfo] = {}
        self._update_gpu_info()
    
    def _run_command(self, command: str) -> str:
        """
        执行命令并返回输出
        
        Args:
            command: 要执行的命令
        
        Returns:
            命令输出
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout
        except Exception as e:
            print(f"执行命令失败: {command}, 错误: {e}")
            return ""
    
    def _update_gpu_info(self):
        """更新GPU信息"""
        try:
            output = self._run_command("nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits")
            
            if not output:
                print("警告: 无法获取GPU信息，使用默认值")
                self._set_default_gpu_info()
                return
            
            lines = output.strip().split('\n')
            
            for line in lines:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 5:
                    gpu_id = int(parts[0])
                    if gpu_id in self.gpu_ids:
                        self.gpu_info[gpu_id] = GPUInfo(
                            gpu_id=gpu_id,
                            name=parts[1],
                            memory_used=int(parts[2]),
                            memory_total=int(parts[3]),
                            memory_free=int(parts[3]) - int(parts[2]),
                            utilization=int(parts[4]),
                            processes=self._get_gpu_process_count(gpu_id)
                        )
            
            # 为未检测到的GPU设置默认值
            for gpu_id in self.gpu_ids:
                if gpu_id not in self.gpu_info:
                    self.gpu_info[gpu_id] = GPUInfo(
                        gpu_id=gpu_id,
                        name="Unknown",
                        memory_used=0,
                        memory_total=81920,  # 默认80GB
                        memory_free=81920,
                        utilization=0,
                        processes=0
                    )
        
        except Exception as e:
            print(f"更新GPU信息失败: {e}")
            self._set_default_gpu_info()
    
    def _get_gpu_process_count(self, gpu_id: int) -> int:
        """
        获取指定GPU上的进程数
        
        Args:
            gpu_id: GPU ID
        
        Returns:
            进程数
        """
        try:
            output = self._run_command(f"nvidia-smi -i {gpu_id} --query-compute-apps=pid --format=csv,noheader")
            if output:
                return len([line for line in output.strip().split('\n') if line.strip()])
            return 0
        except:
            return 0
    
    def _set_default_gpu_info(self):
        """设置默认GPU信息（当nvidia-smi不可用时）"""
        for gpu_id in self.gpu_ids:
            self.gpu_info[gpu_id] = GPUInfo(
                gpu_id=gpu_id,
                name="GPU (nvidia-smi不可用)",
                memory_used=0,
                memory_total=81920,
                memory_free=81920,
                utilization=0,
                processes=0
            )
    
    def get_available_gpus(self, min_memory_mb: int = 10000) -> List[GPUInfo]:
        """
        获取可用的GPU列表
        
        Args:
            min_memory_mb: 最小可用内存要求（MB）
        
        Returns:
            可用GPU列表，按可用性评分排序
        """
        self._update_gpu_info()
        
        available_gpus = [
            gpu for gpu in self.gpu_info.values()
            if gpu.is_available and gpu.memory_free >= min_memory_mb
        ]
        
        # 按评分排序，分数高的在前
        available_gpus.sort(key=lambda x: x.score, reverse=True)
        
        return available_gpus
    
    def allocate_gpus(self, num_gpus: int, min_memory_mb: int = 10000) -> List[int]:
        """
        分配指定数量的GPU
        
        Args:
            num_gpus: 需要的GPU数量
            min_memory_mb: 每个GPU的最小可用内存要求（MB）
        
        Returns:
            分配的GPU ID列表
        """
        available_gpus = self.get_available_gpus(min_memory_mb)
        
        if len(available_gpus) < num_gpus:
            print(f"警告: 只找到 {len(available_gpus)} 个可用GPU，需要 {num_gpus} 个")
            num_gpus = len(available_gpus)
        
        allocated_gpus = [gpu.gpu_id for gpu in available_gpus[:num_gpus]]
        
        return allocated_gpus
    
    def print_gpu_status(self):
        """打印GPU状态"""
        self._update_gpu_info()
        
        print("\n" + "="*80)
        print("GPU状态监控")
        print("="*80)
        print(f"{'GPU ID':<8} {'名称':<30} {'内存使用':<15} {'GPU利用率':<12} {'进程数':<8} {'状态':<10}")
        print("-"*80)
        
        for gpu_id in sorted(self.gpu_info.keys()):
            gpu = self.gpu_info[gpu_id]
            memory_info = f"{gpu.memory_used:6d}/{gpu.memory_total:6d} MB ({gpu.memory_usage_percent:5.1f}%)"
            utilization_info = f"{gpu.utilization:3d}%"
            status = "✓ 可用" if gpu.is_available else "✗ 不可用"
            
            print(f"{gpu_id:<8} {gpu.name[:30]:<30} {memory_info:<15} {utilization_info:<12} {gpu.processes:<8} {status:<10}")
        
        print("="*80)
    
    def get_best_gpu(self, min_memory_mb: int = 10000) -> Optional[int]:
        """
        获取最佳可用GPU
        
        Args:
            min_memory_mb: 最小可用内存要求（MB）
        
        Returns:
            最佳GPU ID，如果没有可用GPU则返回None
        """
        available_gpus = self.get_available_gpus(min_memory_mb)
        
        if available_gpus:
            return available_gpus[0].gpu_id
        
        return None


def test_gpu_manager():
    """测试GPU管理器"""
    print("测试GPU管理器...")
    
    # 创建GPU管理器，监控5个GPU（0-4）
    gpu_manager = GPUManager(gpu_ids=[0, 1, 2, 3, 4])
    
    # 打印GPU状态
    gpu_manager.print_gpu_status()
    
    # 获取可用GPU
    available_gpus = gpu_manager.get_available_gpus()
    print(f"\n可用GPU数量: {len(available_gpus)}")
    for gpu in available_gpus:
        print(f"  GPU {gpu.gpu_id}: 评分={gpu.score:.1f}, 空闲内存={gpu.memory_free}MB")
    
    # 分配2个GPU
    allocated = gpu_manager.allocate_gpus(2)
    print(f"\n分配的GPU: {allocated}")
    
    # 获取最佳GPU
    best_gpu = gpu_manager.get_best_gpu()
    print(f"最佳GPU: {best_gpu}")


if __name__ == "__main__":
    test_gpu_manager()
