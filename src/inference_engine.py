"""
推理引擎模块
负责模型的推理过程和结果生成
"""

import torch
from typing import Dict, Any, Optional
from qwen_vl_utils import process_vision_info
from .config import Config
from .model_manager import ModelManager
from .prompt_manager import PromptManager
from .video_processor import VideoProcessor


class InferenceEngine:
    """推理引擎，负责处理视频标注的推理过程"""
    
    def __init__(self, config: Optional[Config] = None):
        """
        初始化推理引擎
        
        Args:
            config: 配置对象，如果为None则使用默认配置
        """
        self.config = config or Config()
        self.model_manager = ModelManager(config)
        self.prompt_manager = PromptManager()
        self.video_processor = VideoProcessor(use_ffmpeg=self.config.video.use_ffmpeg_metadata)
        
        self._is_initialized = False
    
    def initialize(self):
        """初始化推理引擎"""
        if self._is_initialized:
            return
        
        self.model_manager.load_model()
        self._is_initialized = True
    
    def annotate_video(self, video_path: str, 
                       prompt: Optional[str] = None,
                       fps: Optional[float] = None,
                       max_frames: Optional[int] = None) -> str:
        """
        对视频进行标注
        
        Args:
            video_path: 视频文件路径
            prompt: 自定义提示词，如果为None则使用默认EMCAST提示词
            fps: 视频采样帧率，如果为None则使用配置中的默认值
            max_frames: 最大帧数限制
        
        Returns:
            标注结果字符串
        """
        if not self._is_initialized:
            self.initialize()
        
        # 验证视频文件
        is_valid, error_msg = self.video_processor.validate_video(video_path)
        if not is_valid:
            raise ValueError(error_msg)
        
        # 获取视频元数据
        video_metadata = self.video_processor.get_video_metadata(video_path)
        
        # 生成提示词
        if prompt is None:
            prompt = self.prompt_manager.get_emcast_prompt(video_metadata.to_dict())
        
        # 准备视频输入
        video_fps = fps if fps is not None else self.config.video.fps
        video_input = self.video_processor.prepare_video_input(
            video_path, fps=video_fps, max_frames=max_frames
        )
        
        # 构造消息
        messages = [
            {
                "role": "user",
                "content": [
                    video_input,
                    {"text": prompt},
                ],
            }
        ]
        
        # 预处理
        processor = self.model_manager.get_processor()
        model = self.model_manager.get_model()
        
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to("cuda")  # 使用默认的cuda设备（在设置CUDA_VISIBLE_DEVICES后为GPU 0）
        
        # 生成结果
        with torch.no_grad():
            generated_ids = model.generate(
                **inputs,
                **self.config.get_generation_kwargs()
            )
            generated_ids_trimmed = [
                out_ids[len(in_ids):] 
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            output_text = processor.batch_decode(
                generated_ids_trimmed, 
                skip_special_tokens=True, 
                clean_up_tokenization_spaces=False
            )[0]
        
        return output_text
    
    def batch_annotate(self, video_paths: list, 
                     prompt: Optional[str] = None,
                     fps: Optional[float] = None) -> Dict[str, str]:
        """
        批量标注视频
        
        Args:
            video_paths: 视频文件路径列表
            prompt: 自定义提示词
            fps: 视频采样帧率
        
        Returns:
            字典，键为视频路径，值为标注结果
        """
        results = {}
        
        for video_path in video_paths:
            try:
                print(f"正在处理视频: {video_path}")
                result = self.annotate_video(video_path, prompt, fps)
                results[video_path] = result
                print(f"完成: {video_path}")
            except Exception as e:
                print(f"处理失败 {video_path}: {str(e)}")
                results[video_path] = f"错误: {str(e)}"
        
        return results
    
    def get_video_info(self, video_path: str) -> str:
        """
        获取视频信息
        
        Args:
            video_path: 视频文件路径
        
        Returns:
            格式化的视频信息字符串
        """
        return self.video_processor.get_video_info_string(video_path)
    
    def cleanup(self):
        """清理资源"""
        if self.model_manager.is_loaded():
            self.model_manager.unload_model()
        self._is_initialized = False