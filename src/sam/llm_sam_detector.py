import cv2
import base64
import json
import numpy as np
import torch
import os
from segment_anything import sam_model_registry, SamPredictor
from typing import List, Dict, Any, Optional

from src.models.config import Config
from src.models.model_manager import ModelManager


class LLM_SAM_Detector:
    def __init__(self, sam_model_path=None):
        self.sam_model_path = sam_model_path or "/data/data/xzy/CulturalVideoAnnotation/models/sam_vit_b_01ec64.pth"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self._load_sam()
        self._init_llm()
    
    def _load_sam(self):
        sam = sam_model_registry["vit_b"](checkpoint=self.sam_model_path)
        sam.to(device=self.device)
        self.sam_predictor = SamPredictor(sam)
    
    def _init_llm(self):
        self.config = Config()
        self.config.model.model_type = "glm"
        self.model_manager = ModelManager(self.config)
    
    def _call_llm_grounding(self, image_path: str) -> List[Dict[str, Any]]:
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        image = cv2.imread(image_path)
        h, w = image.shape[:2]
        
        prompt = f"""
请分析这张图片，识别其中的主要建筑或文化符号主体。

图片尺寸：{w} x {h} 像素

请严格按照以下JSON格式输出，不要包含任何其他文字：
{{
  "objects": [
    {{
      "name": "主体名称",
      "bbox": [x1, y1, x2, y2]
    }}
  ]
}}

说明：
- bbox是矩形边界框，格式为[x1, y1, x2, y2]
- x1, y1是左上角像素坐标，x2, y2是右下角像素坐标
- 坐标值必须在0到图片实际尺寸范围内（宽度0-{w}，高度0-{h}）
- 如果图片中有多个主要建筑，请列出所有建筑
- 如果图片中没有明显的建筑，请返回空列表

请仔细观察图片内容，确保边界框准确框住建筑的主体部分。
"""
        
        content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}"
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
        
        try:
            result = self.model_manager.call_glm_api(messages)
            
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = result[json_start:json_end]
                data = json.loads(json_str)
                
                objects = []
                for obj in data.get('objects', []):
                    bbox = obj.get('bbox', [])
                    if len(bbox) == 4:
                        objects.append({
                            'name': obj.get('name', 'unknown'),
                            'bbox': [int(x) for x in bbox]
                        })
                return objects
            else:
                return []
                
        except Exception as e:
            return []
    
    def _scale_bbox(self, bbox: List[int], w: int, h: int) -> List[int]:
        x1, y1, x2, y2 = bbox
        
        if x2 <= 1000 and y2 <= 1000:
            scale_x = w / 1000.0
            scale_y = h / 1000.0
            return [
                int(x1 * scale_x),
                int(y1 * scale_y),
                int(x2 * scale_x),
                int(y2 * scale_y)
            ]
        
        return bbox
    
    def _sam_segment(self, image: np.ndarray, bbox: List[int]) -> Optional[np.ndarray]:
        self.sam_predictor.set_image(image)
        
        x1, y1, x2, y2 = bbox
        input_box = np.array([x1, y1, x2, y2])
        
        masks, scores, logits = self.sam_predictor.predict(
            box=input_box,
            multimask_output=False
        )
        
        if masks is not None and len(masks) > 0:
            return masks[0]
        return None
    
    def detect(self, image_path: str) -> Dict[str, Any]:
        image = cv2.imread(image_path)
        if image is None:
            return {}
        
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w = image_rgb.shape[:2]
        
        objects = self._call_llm_grounding(image_path)
        
        results = []
        for i, obj in enumerate(objects):
            raw_bbox = obj['bbox']
            scaled_bbox = self._scale_bbox(raw_bbox, w, h)
            mask = self._sam_segment(image_rgb, scaled_bbox)
            
            results.append({
                'name': obj['name'],
                'raw_bbox': raw_bbox,
                'scaled_bbox': scaled_bbox,
                'mask': mask
            })
        
        return {
            'image': image,
            'results': results
        }
    
    def visualize(self, result: Dict[str, Any], output_path: str):
        image = result['image'].copy()
        results = result.get('results', [])
        
        bbox_color = (0, 0, 255)
        mask_color = (0, 255, 0)
        text_color = (255, 255, 255)
        
        for idx, res in enumerate(results):
            x1, y1, x2, y2 = res['scaled_bbox']
            
            cv2.rectangle(image, (x1, y1), (x2, y2), bbox_color, 6)
            
            label = f"{idx + 1}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 3)
            label_x = x1 + 10
            label_y = y1 + label_size[1] + 15
            
            cv2.rectangle(image, 
                         (label_x - 5, label_y - label_size[1] - 10),
                         (label_x + label_size[0] + 5, label_y + 5),
                         bbox_color, -1)
            cv2.putText(image, label, (label_x, label_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, text_color, 3)
            
            mask = res.get('mask')
            if mask is not None:
                print(f"  Visualize: mask {idx+1} shape={mask.shape}, dtype={mask.dtype}, non-zero pixels={mask.sum()}")
                
                if mask.ndim == 2:
                    mask_2d = mask
                else:
                    mask_2d = mask[0] if mask.shape[0] == 1 else mask
                
                h, w = image.shape[:2]
                mask_resized = cv2.resize(mask_2d.astype(np.float32), (w, h))
                mask_binary = (mask_resized > 0.5).astype(np.uint8)
                
                mask_indices = mask_binary > 0
                green_layer = np.zeros((h, w), dtype=np.uint8)
                green_layer[mask_indices] = 255
                
                image[:, :, 0] = np.where(mask_indices, 0, image[:, :, 0])
                image[:, :, 1] = np.where(mask_indices, 
                                         cv2.addWeighted(image[:, :, 1], 0.6, green_layer, 0.4, 0).astype(np.uint8),
                                         image[:, :, 1])
                image[:, :, 2] = np.where(mask_indices, 0, image[:, :, 2])
                
                print(f"  Visualize: mask {idx+1} applied to image")
            else:
                print(f"  Visualize: mask {idx+1} is None")
        
        cv2.imwrite(output_path, image)
        print(f"  Saved to: {output_path}")