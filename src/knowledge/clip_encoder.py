"""
CLIP 文本/图像编码器封装（创新点2 第三阶段：多模态检索）

职责：
- 加载 OpenAI CLIP 模型（默认 ViT-B/32，CPU 可用）
- encode_text：把文化符号描述文本编码为 512 维 embedding
- encode_images：把图片路径列表/PIL帧列表编码为 512 维 embedding
- 供 MultimodalCulturalRetriever 计算"视频关键帧 ↔ 知识库参考向量"的余弦相似度

设计说明：
- CLIP 文本编码器与图像编码器输出在同一共享空间，跨模态余弦相似度合法；
- 知识库 reference_images 字段有有效图片路径时用图像编码器，否则用文本描述编码兜底，
  真实参考图片填入字段后无需改代码即可切换。
"""

from typing import List, Optional, Union

import torch

# CLIP 首次加载可能需要下载权重；按需延迟导入
_clip_module = None
_MODEL_CACHE = {}


def _get_clip():
    global _clip_module
    if _clip_module is None:
        import clip  # noqa
        _clip_module = clip
    return _clip_module


class CLIPEncoder:
    """CLIP 文本/图像编码器单例封装"""

    def __init__(self, model_name: str = "ViT-B/32", device: Optional[str] = None):
        """
        Args:
            model_name: CLIP 模型名（默认 ViT-B/32，最小且快）
            device: 'cuda' / 'cpu'；None 时自动检测
        """
        if model_name in _MODEL_CACHE:
            self.model, self.preprocess = _MODEL_CACHE[model_name]
            self.device = self.model.visual.conv1.weight.device
            return
        clip = _get_clip()
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"--- 加载 CLIP {model_name} (device={device}) ---")
        self.model, self.preprocess = clip.load(model_name, device=device)
        self.model.eval()
        self.device = device
        _MODEL_CACHE[model_name] = (self.model, self.preprocess)

    @property
    def embed_dim(self) -> int:
        return self.model.text_projection.shape[1]

    # ------------------------------------------------------------------ #
    # 文本编码
    # ------------------------------------------------------------------ #
    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        """把文本编码为 L2 归一化后的 embedding（shape=[N, embed_dim]）"""
        clip = _get_clip()
        if isinstance(texts, str):
            texts = [texts]
        tokens = clip.tokenize(texts, truncate=True).to(self.device)
        with torch.no_grad():
            emb = self.model.encode_text(tokens)
        emb = emb / emb.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        return emb.cpu()

    # ------------------------------------------------------------------ #
    # 图像编码
    # ------------------------------------------------------------------ #
    def encode_images(self, images: Union[List[str], List]) -> torch.Tensor:
        """把图片路径列表或 PIL.Image 列表编码为 L2 归一化 embedding

        Args:
            images: 图片路径(str)列表 或 PIL.Image 对象列表
        Returns:
            shape=[N, embed_dim]，L2 归一化
        """
        from PIL import Image
        if not images:
            return torch.zeros(0, self.embed_dim)
        processed = []
        for img in images:
            if isinstance(img, str):
                pil = Image.open(img).convert("RGB")
            else:
                pil = img.convert("RGB") if img.mode != "RGB" else img
            processed.append(self.preprocess(pil))
        batch = torch.stack(processed).to(self.device)
        with torch.no_grad():
            emb = self.model.encode_image(batch)
        emb = emb / emb.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        return emb.cpu()

    def encode_frames_from_video(self, video_path: str,
                                  num_frames: int = 4) -> torch.Tensor:
        """从视频均匀采样关键帧并编码为单个聚合 embedding（均值）

        Returns:
            shape=[embed_dim]，L2 归一化；视频读取失败时返回全零向量
        """
        import cv2
        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total == 0:
            cap.release()
            return torch.zeros(self.embed_dim)
        indices = [int(i * total / num_frames) for i in range(num_frames)]
        from PIL import Image
        frames = []
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        cap.release()
        if not frames:
            return torch.zeros(self.embed_dim)
        emb = self.encode_images(frames)  # [N, D]
        pooled = emb.mean(dim=0)  # 均值聚合
        pooled = pooled / pooled.norm().clamp(min=1e-8)  # 重新归一化
        return pooled

    # ------------------------------------------------------------------ #
    # 余弦相似度（输入已 L2 归一化时等价于点积）
    # ------------------------------------------------------------------ #
    @staticmethod
    def cosine_similarity(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        """a:[D] 或 [N,D], b:[M,D] → 返回 [N,M] 相似度矩阵"""
        if a.dim() == 1:
            a = a.unsqueeze(0)
        if b.dim() == 1:
            b = b.unsqueeze(0)
        return (a @ b.t()).cpu()
