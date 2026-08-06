import cv2
import numpy as np
from typing import List, Dict, Any


class DynamicStream:
    def __init__(self):
        self.flow_history = []
        self.motion_threshold = 2.0
    
    def extract_motion_features(self, flow: np.ndarray) -> Dict[str, float]:
        magnitude, angle = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        
        motion_features = {
            'avg_magnitude': np.mean(magnitude),
            'max_magnitude': np.max(magnitude),
            'std_magnitude': np.std(magnitude),
            'avg_angle': np.mean(angle),
            'motion_ratio': np.sum(magnitude > self.motion_threshold) / magnitude.size
        }
        
        return motion_features
    
    def analyze_sequence(self, flows: List[np.ndarray]) -> Dict[str, Any]:
        features = [self.extract_motion_features(f) for f in flows]
        
        avg_magnitudes = [f['avg_magnitude'] for f in features]
        motion_ratios = [f['motion_ratio'] for f in features]
        
        sequence_analysis = {
            'mean_motion': np.mean(avg_magnitudes),
            'motion_variance': np.var(avg_magnitudes),
            'peak_motion_frame': int(np.argmax(avg_magnitudes)),
            'overall_dynamic_ratio': np.mean(motion_ratios),
            'is_high_motion': np.mean(avg_magnitudes) > self.motion_threshold * 2,
            'temporal_features': features
        }
        
        return sequence_analysis
    
    def detect_motion_events(self, flows: List[np.ndarray]) -> List[int]:
        events = []
        
        for i, flow in enumerate(flows):
            features = self.extract_motion_features(flow)
            if features['avg_magnitude'] > self.motion_threshold * 3:
                events.append(i)
        
        return events