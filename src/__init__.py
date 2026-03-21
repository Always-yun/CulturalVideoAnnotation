"""
Cultural Video Annotation Package
北京文化视频标注系统
"""

__version__ = "1.0.0"
__author__ = "Cultural Video Annotation Team"

from .config import Config
from .model_manager import ModelManager
from .prompt_manager import PromptManager
from .video_processor import VideoProcessor
from .inference_engine import InferenceEngine
from .result_processor import ResultProcessor

__all__ = [
    "Config",
    "ModelManager",
    "PromptManager",
    "VideoProcessor",
    "InferenceEngine",
    "ResultProcessor",
]