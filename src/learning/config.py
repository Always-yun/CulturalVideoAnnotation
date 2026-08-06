"""
学习模块配置
集中管理学习相关的所有配置参数
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LearningConfig:
    """学习模块配置类"""
    
    # 是否启用学习功能
    enabled: bool = False
    
    # 向量数据库配置
    vector_db_path: str = None  # ChromaDB 存储路径
    collection_name: str = "correction_cases"  # 集合名称
    
    # Few-shot 配置
    max_examples_per_query: int = 3  # 每次检索最多返回的示例数
    min_similarity_score: float = 0.6  # 最小相似度阈值
    
    # 场景分类
    scene_categories: List[str] = field(default_factory=lambda: [
        "古都文化",
        "红色文化", 
        "京味文化",
        "创新科技文化",
        "国际时尚文化"
    ])
    
    # 差异分析配置
    diff_min_length: int = 5  # 最小差异长度（字符数）
    ignore_patterns: List[str] = field(default_factory=lambda: [
        r"^\s+$",  # 纯空白
        r"^[，。！？、；：""''（）【】]+$"  # 纯标点
    ])
    
    # Embedding 模型配置
    embedding_model: str = "text2vec-base-chinese"  # 本地 embedding 模型
    embedding_device: str = "cpu"  # embedding 设备
    
    # 数据存储路径
    corrections_dir: str = None  # 修正数据存储目录
    
    def __post_init__(self):
        """初始化路径"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        if self.vector_db_path is None:
            self.vector_db_path = os.path.join(base_dir, "data", "learning", "vector_db")
        
        if self.corrections_dir is None:
            self.corrections_dir = os.path.join(base_dir, "data", "learning", "corrections")
        
        # 确保目录存在
        os.makedirs(self.vector_db_path, exist_ok=True)
        os.makedirs(self.corrections_dir, exist_ok=True)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "enabled": self.enabled,
            "vector_db_path": self.vector_db_path,
            "collection_name": self.collection_name,
            "max_examples_per_query": self.max_examples_per_query,
            "min_similarity_score": self.min_similarity_score,
            "scene_categories": self.scene_categories,
            "embedding_model": self.embedding_model,
            "corrections_dir": self.corrections_dir
        }