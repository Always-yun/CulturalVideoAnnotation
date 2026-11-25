"""
推理引擎模块 (时长自适应时序采样版)
负责模型的推理过程和结果生成
支持本地Qwen模型和GLM-4 API两种模式
"""

import torch
import base64
import os
import tempfile
from typing import Dict, Any, List, Optional
from qwen_vl_utils import process_vision_info
from src.models.config import Config
from src.models.model_manager import ModelManager
from .prompt_manager import PromptManager
from .video_processor import VideoProcessor


def extract_video_frames(video_path: str, num_frames: int = 8) -> list:
    """从视频中提取关键帧并返回base64编码列表"""
    import cv2
    
    frames = []
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if total_frames == 0:
        cap.release()
        return frames
    
    # 均匀采样
    indices = [int(i * total_frames / num_frames) for i in range(num_frames)]
    
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            # 编码为JPEG
            _, buffer = cv2.imencode('.jpg', frame)
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            frames.append(frame_base64)
    
    cap.release()
    return frames


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

        # 文化符号检索器（创新点2：多模态检索 → Top-K 文化候选 → 动态 Prompt）
        # 默认 None = 不检索，C 层仅按中华文化五维闭集判定（保持既有行为）；
        # 注入 src.knowledge.BaseCulturalRetriever 子类后即启用知识库候选。
        self.cultural_retriever = None
        self.cultural_top_k = 5

        # 稳健性处理 use_ffmpeg 属性
        use_ffmpeg = self.config.video.use_ffmpeg_metadata if hasattr(self.config, 'video') and hasattr(self.config.video, 'use_ffmpeg_metadata') else True
        self.video_processor = VideoProcessor(use_ffmpeg=use_ffmpeg)

        self._is_initialized = False
        self.cultural_pipeline = None
        self.last_cultural_trace = None

    def enable_cultural_pipeline(self, mode="multimodal", top_k=5,
                                 kb_path=None, identity_verifier="v2",
                                 scene_mode="structured", text_recognition=True,
                                 retrieval_strategy="legacy"):
        """Attach the innovation2 pipeline; explicit prompts bypass it for internal passes."""
        if mode not in {"keyword", "multimodal"}:
            raise ValueError(f"Unsupported cultural mode: {mode}")
        if mode != "multimodal" and retrieval_strategy != "legacy":
            raise ValueError("evidence_v1 requires --culture-mode multimodal")
        if top_k < 1:
            raise ValueError("top_k must be positive")
        from .cultural_rag import CulturalRAGPipeline
        from ..knowledge.symbol_kb import SymbolKnowledgeBase
        from ..knowledge.retriever import KeywordCulturalRetriever
        from ..knowledge.rejection_gate import RejectionGate
        kb = SymbolKnowledgeBase(json_path=kb_path)
        if mode == "multimodal":
            from ..knowledge.multimodal_retriever import MultimodalCulturalRetriever
            retriever = MultimodalCulturalRetriever(kb=kb, ranking_strategy=retrieval_strategy)
        else:
            retriever = KeywordCulturalRetriever(kb=kb)
        verifier = None
        if identity_verifier == "v2":
            from ..knowledge.identity_verifier_v2 import IdentityVerifierV2
            verifier = IdentityVerifierV2(kb=kb, model_manager=self.model_manager)
        elif identity_verifier != "off":
            raise ValueError(f"Unsupported identity verifier: {identity_verifier}")
        self.cultural_pipeline = CulturalRAGPipeline(
            engine=self, kb=kb, retriever=retriever, top_k=top_k,
            rejection_gate=RejectionGate(), identity_verifier=verifier,
            scene_mode=scene_mode, text_recognition=text_recognition,
            output_root=os.path.join(self.config.paths.output_dir, "cultural_traces"))

    def set_cultural_retriever(self, retriever, top_k: int = 5):
        """挂载文化符号检索器（如 KeywordCulturalRetriever / 未来的多模态检索器）"""
        self.cultural_retriever = retriever
        self.cultural_top_k = top_k
    
    def initialize(self):
        """初始化推理引擎"""
        if self._is_initialized:
            return
        
        self.model_manager.load_model()
        self._is_initialized = True
    
    def _video_to_base64(self, video_path: str) -> str:
        """将视频文件转换为base64编码"""
        with open(video_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    def annotate_video(self, video_path: str,
                       prompt: Optional[str] = None,
                       fps: Optional[float] = None,
                       max_frames: Optional[int] = None,
                       cultural_candidates: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        对视频进行标注

        Args:
            video_path: 视频文件路径
            prompt: 自定义提示词，如果为None则使用默认EMCAST提示词
            fps: 视频采样帧率，如果为None则使用配置中的默认值
            max_frames: 最大帧数限制
            cultural_candidates: 显式指定的知识库 Top-K 文化符号候选（dict 列表）；
                为 None 且已挂载 cultural_retriever 时自动检索（本期 retriever 默认
                不挂载，保持仅按五维闭集判定的行为）

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

        # Only public annotation calls enter RAG. Pass-1/Pass-2 use explicit prompts.
        if prompt is None and cultural_candidates is None and self.cultural_pipeline is not None:
            self.last_cultural_trace = self.cultural_pipeline.run(
                video_path, controlled=True, save=True)
            self.cultural_pipeline.save_trace(
                [self.last_cultural_trace], self.last_cultural_trace["output_dir"])
            return self.last_cultural_trace["final_annotation"]

        # 生成提示词（中华文化五维闭集 + 可选知识库 Top-K 候选注入）
        if prompt is None:
            # 未显式给候选但挂载了检索器 → 自动检索（scene_text 预留给 VLM 首帧描述）
            if cultural_candidates is None and self.cultural_retriever is not None:
                video_context = {
                    "video_path": video_path,
                    "scene_text": "",
                    "keywords": [],
                }
                retrieved = self.cultural_retriever.retrieve(
                    video_context, top_k=self.cultural_top_k)
                cultural_candidates = [c.to_symbol_dict() for c in retrieved]
            prompt = self.prompt_manager.get_emcast_prompt(
                video_metadata.to_dict(),
                video_path=video_path,
                cultural_candidates=cultural_candidates,
            )
        
        # 检查是否使用GLM-4 API模式
        if self.model_manager.is_glm_mode():
            return self._annotate_with_glm_api(video_path, prompt)
        
        # Qwen本地模型模式
        return self._annotate_with_qwen(
            video_path, prompt, video_metadata, fps,
            max_frames if max_frames is not None else self.config.video.max_frames)
    
    def _annotate_with_qwen(self, video_path: str, prompt: str, 
                           video_metadata, fps: Optional[float], 
                           max_frames: Optional[int]) -> str:
        """使用Qwen本地模型进行标注"""
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
        
        # 过滤模型不支持的参数
        for key in ['pixel_values_videos', 'video_grid_thw']:
            if key in inputs:
                inputs.pop(key)
        
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
    
    def _annotate_with_glm_api(self, video_path: str, prompt: str) -> str:
        """使用GLM-4 API进行标注（先直接发送，报错时自动压缩重试）"""
        print(f"--- 使用 GLM-4 API 处理视频: {os.path.basename(video_path)} ---")
        
        # 尝试直接发送，如果失败则压缩重试
        return self._try_annotate_glm_with_fallback(video_path, prompt)
    
    def _try_annotate_glm_with_fallback(self, video_path: str, prompt: str) -> str:
        """
        先直接发送原始视频，如果API报错则压缩重试
        
        Args:
            video_path: 视频文件路径
            prompt: 提示词
            
        Returns:
            API返回的标注结果
        """
        # 第一次尝试：直接使用原始视频
        try:
            print("--- 第一次尝试：直接发送原始视频 ---")
            return self._call_glm_api_with_video(video_path, prompt)
        except RuntimeError as e:
            error_msg = str(e)
            print(f"--- 直接发送失败: {error_msg[:200]} ---")
            
            # 检查是否是视频大小/格式相关的错误
            size_related_errors = ['size', 'limit', 'too large', 'max_bytes', 
                                   'max_size', 'exceeded', '413', 'payload',
                                   'invalid', 'video', 'encode']
            if any(kw in error_msg.lower() for kw in size_related_errors):
                print("--- 检测到视频大小/格式问题，尝试压缩后重试 ---")
                compressed_path = self.video_processor.compress_video_for_api(video_path)
                if compressed_path != video_path:
                    try:
                        print("--- 第二次尝试：使用压缩后的视频 ---")
                        return self._call_glm_api_with_video(compressed_path, prompt)
                    except RuntimeError as e2:
                        print(f"--- 压缩后仍然失败: {str(e2)[:200]} ---")
                        raise RuntimeError(f"GLM-4 API调用失败（压缩后仍失败）: {str(e2)}")
                else:
                    print("--- 压缩未改变文件大小，无法重试 ---")
                    raise e
            else:
                # 非视频大小相关错误，直接抛出
                raise
    
    def _call_glm_api_with_video(self, video_path: str, prompt: str) -> str:
        """
        使用指定视频路径调用GLM-4 API
        
        Args:
            video_path: 视频文件路径
            prompt: 提示词
            
        Returns:
            API返回的标注结果
        """
        print(f"--- 正在读取视频文件: {os.path.basename(video_path)} ---")
        with open(video_path, 'rb') as f:
            video_bytes = f.read()
        video_base64 = base64.b64encode(video_bytes).decode('utf-8')
        print(f"--- 视频文件大小: {len(video_bytes) / 1024 / 1024:.2f} MB ---")
        print(f"--- Base64编码后大小: {len(video_base64) / 1024:.2f} KB ---")
        
        content = [
            {
                "type": "video_url",
                "video_url": {
                    "url": f"data:video/mp4;base64,{video_base64}"
                }
            },
            {
                "type": "text", 
                "text": prompt
            }
        ]
        
        messages = [
            {
                "role": "user",
                "content": content
            }
        ]
        
        print(f"--- 提示词长度: {len(prompt)} ---")
        print(f"--- 内容类型: {[item['type'] for item in messages[0]['content']]} ---")
        
        # 调用GLM-4 API
        result = self.model_manager.call_glm_api(messages)
        print("--- GLM-4 API 调用完成 ---")
        
        return result
    
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