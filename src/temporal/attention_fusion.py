import cv2
import numpy as np
from typing import List, Dict, Any


class AttentionFusion:
    def __init__(self):
        pass
    
    def compute_spatial_attention(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        edge_attention = np.abs(laplacian)
        
        normalized = (edge_attention - np.min(edge_attention)) / (
            np.max(edge_attention) - np.min(edge_attention) + 1e-8
        )
        
        return normalized
    
    def compute_temporal_attention(self, flows: List[np.ndarray]) -> np.ndarray:
        if len(flows) == 0:
            return None
        
        magnitudes = []
        for flow in flows:
            mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            magnitudes.append(mag)
        
        avg_magnitude = np.mean(magnitudes, axis=0)
        
        temporal_attn = 1.0 - (avg_magnitude / (np.max(avg_magnitude) + 1e-8))
        
        return temporal_attn
    
    def fuse_masks(self, masks: List[np.ndarray], 
                   spatial_attn: np.ndarray, 
                   temporal_attn: np.ndarray) -> np.ndarray:
        if len(masks) == 0:
            return None
        
        weights = []
        for i, mask in enumerate(masks):
            mask_float = mask.astype(np.float32) / 255.0
            
            weight = mask_float * spatial_attn
            if temporal_attn is not None:
                weight *= temporal_attn
            
            weights.append(weight)
        
        fused = np.mean(weights, axis=0)
        
        fused_binary = (fused > 0.5).astype(np.uint8) * 255
        
        return fused_binary
    
    def multi_scale_fusion(self, masks: List[np.ndarray]) -> np.ndarray:
        if len(masks) == 0:
            return None
        
        scales = [0.5, 1.0, 2.0]
        fused_results = []
        
        for scale in scales:
            scaled_masks = []
            for mask in masks:
                h, w = mask.shape[:2]
                new_h, new_w = int(h * scale), int(w * scale)
                scaled = cv2.resize(mask, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                scaled_masks.append(scaled)
            
            avg_mask = np.mean(scaled_masks, axis=0)
            resized_back = cv2.resize(avg_mask, (w, h), interpolation=cv2.INTER_LINEAR)
            fused_results.append(resized_back)
        
        final_fusion = np.mean(fused_results, axis=0)
        binary = (final_fusion > 127).astype(np.uint8) * 255
        
        return binary