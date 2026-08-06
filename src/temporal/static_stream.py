import cv2
import numpy as np
from typing import List, Dict, Any


class StaticStream:
    def __init__(self):
        self.stability_threshold = 0.95
    
    def compute_stability_mask(self, frames: List[np.ndarray]) -> np.ndarray:
        if len(frames) < 3:
            return np.ones_like(frames[0][..., 0]) * 255
        
        frames_gray = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
        
        diffs = []
        for i in range(1, len(frames_gray)):
            diff = cv2.absdiff(frames_gray[i-1], frames_gray[i])
            diffs.append(diff)
        
        avg_diff = np.mean(diffs, axis=0)
        
        stability_mask = (avg_diff < 10).astype(np.uint8) * 255
        
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        stability_mask = cv2.morphologyEx(stability_mask, cv2.MORPH_CLOSE, kernel)
        
        return stability_mask
    
    def extract_static_features(self, frames: List[np.ndarray]) -> Dict[str, float]:
        stability_mask = self.compute_stability_mask(frames)
        
        h, w = stability_mask.shape[:2]
        total_pixels = h * w
        
        static_ratio = np.sum(stability_mask > 0) / total_pixels
        
        contours, _ = cv2.findContours(
            stability_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        static_features = {
            'static_ratio': static_ratio,
            'num_static_regions': len(contours),
            'is_dominantly_static': static_ratio > self.stability_threshold,
            'static_area': np.sum(stability_mask > 0)
        }
        
        return static_features
    
    def find_background(self, frames: List[np.ndarray]) -> np.ndarray:
        stability_mask = self.compute_stability_mask(frames)
        
        background = np.median(frames, axis=0).astype(np.uint8)
        
        background[stability_mask == 0] = 0
        
        return background