"""
模型管理模块
负责模型的加载、初始化和管理
"""

import torch
from transformers import Qwen3_5ForConditionalGeneration, AutoProcessor
from typing import Optional
from .config import Config


class ModelManager:
    """模型管理器，负责加载和管理Qwen3.5模型"""
    
    def __init__(self, config: Optional[Config] = None):
        """
        初始化模型管理器
        
        Args:
            config: 配置对象，如果为None则使用默认配置
        """
        self.config = config or Config()
        self.model = None
        self.processor = None
        self._is_loaded = False
    
    def load_model(self):
        """加载模型和处理器"""
        if self._is_loaded:
            print("模型已加载，跳过重复加载")
            return
        
        print(f"--- 正在加载 Qwen 3.5-9B 模型 ---")
        
        # 加载处理器
        self.processor = AutoProcessor.from_pretrained(
            self.config.model.model_path,
            trust_remote_code=self.config.model.trust_remote_code
        )
        
        # 加载模型
        self.model = Qwen3_5ForConditionalGeneration.from_pretrained(
            self.config.model.model_path,
            **self.config.get_model_kwargs()
        ).eval()
        
        self._is_loaded = True
        print("--- 模型加载完成 ---")
    
    def get_model(self):
        """获取模型实例"""
        if not self._is_loaded:
            self.load_model()
        return self.model
    
    def get_processor(self):
        """获取处理器实例"""
        if not self._is_loaded:
            self.load_model()
        return self.processor
    
    def is_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._is_loaded
    
    def unload_model(self):
        """卸载模型释放内存"""
        if self._is_loaded:
            del self.model
            del self.processor
            self.model = None
            self.processor = None
            self._is_loaded = False
            torch.cuda.empty_cache()
            print("--- 模型已卸载 ---")