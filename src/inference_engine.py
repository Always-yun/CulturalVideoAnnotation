"""
推理引擎模块 (时长自适应时序采样版)
负责模型的推理过程和结果生成
通过动态计算自适应 nframes，兼顾长视频/高频转场细节提取与24GB显存安全
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
        
        # 稳健性处理 use_ffmpeg 属性
        use_ffmpeg = self.config.video.use_ffmpeg_metadata if hasattr(self.config, 'video') and hasattr(self.config.video, 'use_ffmpeg_metadata') else True
        self.video_processor = VideoProcessor(use_ffmpeg=use_ffmpeg)
        
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
        
        # 生成提示词（传递视频路径用于动态场景检测）
        if prompt is None:
            prompt = self.prompt_manager.get_emcast_prompt(
                video_metadata.to_dict(), 
                video_path=video_path
            )
        
        # 准备视频输入
        video_fps = fps if fps is not None else self.config.video.fps
        video_input = self.video_processor.prepare_video_input(
            video_path, fps=video_fps, max_frames=max_frames
        )
        
        # ============================================================
        # 核心学术升级点：时长自适应时序采样，拒绝死板的固定抽 8 帧
        # ============================================================
        if isinstance(video_input, dict):
            # 1. 强行弹出原有 fps 键，持续死锁底层冲突报错
            video_input.pop("fps", None) 
            
            # 2. 完美对齐视频底层硬件天花板，彻底消除 limit[602112] 越界警告
            # 602112 是 Qwen 视频处理的最高像素极限，既能完美识别中关村标语文字，又符合原生位置编码规范
            video_input["max_pixels"] = 602112 
            
            # 3. 动态自适应抽帧策略
            meta_dict = video_metadata.to_dict() if hasattr(video_metadata, 'to_dict') else {}
            try:
                # 安全解析视频时长
                raw_duration = meta_dict.get('duration', 10.0)
                duration = float(raw_duration) if raw_duration and str(raw_duration).strip() != '[ ]' else 10.0
            except (ValueError, TypeError):
                duration = 10.0
            
            # 比例公式：时长 * 目标帧率 (例如 30秒 * 1fps = 30帧)
            # max(8, ...): 确保哪怕超短视频也有 8 帧作为语义基准底线
            # min(32, ...): 在 24GB 显存和高清画质下，32帧是防爆、防OOM的铁血红线上限
            dynamic_nframes = max(8, min(32, int(duration * video_fps)))
            
            # 4. 优先级判定：若主程序或命令行传入了明确的 max_frames 则听从指令，否则启用自动智能适配
            if max_frames is not None:
                video_input["nframes"] = max_frames
            else:
                video_input["nframes"] = dynamic_nframes
                
            print(f"--- [时序调优] 动态时空对齐: 检测到视频时长 {duration:.2f} 秒，系统自动智能抽取 {video_input['nframes']} 帧进行稠密细节特征提取 ---")
        # ============================================================
        
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
        
        # 多卡安全对齐
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(model.device)  
        
        # 净化生成参数
        gen_kwargs = self.config.get_generation_kwargs()
        if not gen_kwargs.get("do_sample", False):
            gen_kwargs.pop("temperature", None)
            gen_kwargs.pop("top_p", None)
        
        # 生成结果
        with torch.no_grad():
            generated_ids = model.generate(
                **inputs,
                **gen_kwargs
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
        """批量标注视频"""
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
        """获取视频信息"""
        return self.video_processor.get_video_info_string(video_path)
    
    def cleanup(self):
        """清理资源"""
        if self.model_manager.is_loaded():
            self.model_manager.unload_model()
        self._is_initialized = False