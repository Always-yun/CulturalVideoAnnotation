"""
配置管理模块
集中管理所有配置参数，便于维护和修改
"""

import os
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class GPUConfig:
    """GPU相关配置"""
    device_id: int = 5
    visible_devices: str = "5"
    torch_dtype: str = "bfloat16"


@dataclass
class ModelConfig:
    """模型相关配置"""
    model_path: str = "/data/data/xzy/CulturalVideoAnnotation/models/Qwen3.5-9B"
    trust_remote_code: bool = True
    device_map: Dict[str, int] = None
    
    def __post_init__(self):
        if self.device_map is None:
            # 当设置CUDA_VISIBLE_DEVICES后，实际的GPU编号会改变
            # 默认使用GPU 0（在设置CUDA_VISIBLE_DEVICES="5"后，这对应物理GPU 5）
            self.device_map = {"": 0}


@dataclass
class VideoConfig:
    """视频处理配置"""
    fps: float = 0.5
    max_frames: int = None
    use_ffmpeg_metadata: bool = True


@dataclass
class GenerationConfig:
    """文本生成配置"""
    max_new_tokens: int = 4096
    temperature: float = 0.1
    top_p: float = 0.9
    repetition_penalty: float = 1.1
    do_sample: bool = False


@dataclass
class PathConfig:
    """路径配置"""
    base_dir: str = "/data/data/xzy/CulturalVideoAnnotation"
    data_dir: str = None
    models_dir: str = None
    output_dir: str = None
    
    def __post_init__(self):
        if self.data_dir is None:
            self.data_dir = os.path.join(self.base_dir, "data")
        if self.models_dir is None:
            self.models_dir = os.path.join(self.base_dir, "models")
        if self.output_dir is None:
            self.output_dir = os.path.join(self.base_dir, "outputs")


class Config:
    """主配置类，整合所有子配置"""
    
    def __init__(self):
        self.gpu = GPUConfig()
        self.model = ModelConfig()
        self.video = VideoConfig()
        self.generation = GenerationConfig()
        self.paths = PathConfig()
        
        self._setup_environment()
    
    def _setup_environment(self):
        """设置环境变量"""
        os.environ["CUDA_VISIBLE_DEVICES"] = self.gpu.visible_devices
    
    def get_model_kwargs(self) -> Dict[str, Any]:
        """获取模型加载参数"""
        return {
            "torch_dtype": self.gpu.torch_dtype,
            "device_map": self.model.device_map,
            "trust_remote_code": self.model.trust_remote_code
        }
    
    def get_generation_kwargs(self) -> Dict[str, Any]:
        """获取生成参数"""
        return {
            "max_new_tokens": self.generation.max_new_tokens,
            "temperature": self.generation.temperature,
            "top_p": self.generation.top_p,
            "repetition_penalty": self.generation.repetition_penalty,
            "do_sample": self.generation.do_sample
        }
    
    def update(self, **kwargs):
        """动态更新配置"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                # 尝试更新子配置
                for attr_name in dir(self):
                    attr = getattr(self, attr_name)
                    if hasattr(attr, key):
                        setattr(attr, key, value)
                        break


# 全局配置实例
config = Config()