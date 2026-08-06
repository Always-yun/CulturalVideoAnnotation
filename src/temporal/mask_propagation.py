import cv2
import numpy as np
from typing import List, Dict, Any, Optional


class MaskPropagation:
    def __init__(self, method: str = "bbox_transfer"):
        self.method = method
        
        if method == "optical_flow":
            self._init_optical_flow()
    
    def _init_optical_flow(self):
        self.flow_params = dict(
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=cv2.OPTFLOW_FARNEBACK_GAUSSIAN
        )
    
    def get_mask_bbox(self, mask: np.ndarray) -> Optional[List[int]]:
        if mask is None or mask.sum() == 0:
            return None
        
        if mask.ndim == 3:
            mask = mask[0]
        
        y_coords, x_coords = np.where(mask > 0)
        
        if len(x_coords) == 0:
            return None
        
        x_min, x_max = int(x_coords.min()), int(x_coords.max())
        y_min, y_max = int(y_coords.min()), int(y_coords.max())
        
        return [x_min, y_min, x_max, y_max]
    
    def expand_bbox(self, bbox: List[int], expand_ratio: float = 0.1, 
                    img_w: int = None, img_h: int = None) -> List[int]:
        x1, y1, x2, y2 = bbox
        
        w = x2 - x1
        h = y2 - y1
        
        expand_w = int(w * expand_ratio)
        expand_h = int(h * expand_ratio)
        
        x1 = max(0, x1 - expand_w)
        y1 = max(0, y1 - expand_h)
        x2 = x2 + expand_w
        y2 = y2 + expand_h
        
        if img_w is not None:
            x2 = min(img_w - 1, x2)
        if img_h is not None:
            y2 = min(img_h - 1, y2)
        
        return [x1, y1, x2, y2]
    
    def compute_flow(self, prev_frame: np.ndarray, curr_frame: np.ndarray) -> np.ndarray:
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
        
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, curr_gray, None, **self.flow_params
        )
        
        return flow
    
    def warp_mask(self, mask: np.ndarray, flow: np.ndarray) -> np.ndarray:
        h, w = mask.shape[:2]
        
        y_coords, x_coords = np.where(mask > 0)
        
        if len(x_coords) == 0:
            return np.zeros_like(mask)
        
        x_new = x_coords + flow[y_coords, x_coords, 0]
        y_new = y_coords + flow[y_coords, x_coords, 1]
        
        valid_mask = (
            (x_new >= 0) & (x_new < w) &
            (y_new >= 0) & (y_new < h)
        )
        
        x_valid = x_new[valid_mask].astype(np.int32)
        y_valid = y_new[valid_mask].astype(np.int32)
        
        propagated_mask = np.zeros_like(mask)
        propagated_mask[y_valid, x_valid] = 255
        
        return propagated_mask
    
    def propagate(self, prev_frame: np.ndarray, curr_frame: np.ndarray, 
                  prev_mask: np.ndarray, sam_predictor=None) -> np.ndarray:
        if self.method == "optical_flow":
            flow = self.compute_flow(prev_frame, curr_frame)
            propagated_mask = self.warp_mask(prev_mask, flow)
            return propagated_mask
        
        elif self.method == "bbox_transfer":
            if sam_predictor is None:
                bbox = self.get_mask_bbox(prev_mask)
                if bbox is None:
                    return np.zeros_like(prev_mask)
                
                h, w = prev_frame.shape[:2]
                expanded_bbox = self.expand_bbox(bbox, expand_ratio=0.1, img_w=w, img_h=h)
                
                propagated_mask = np.zeros_like(prev_mask)
                x1, y1, x2, y2 = expanded_bbox
                propagated_mask[y1:y2, x1:x2] = 255
                return propagated_mask
            
            bbox = self.get_mask_bbox(prev_mask)
            if bbox is None:
                return np.zeros_like(prev_mask)
            
            h, w = curr_frame.shape[:2]
            expanded_bbox = self.expand_bbox(bbox, expand_ratio=0.1, img_w=w, img_h=h)
            
            sam_predictor.set_image(curr_frame)
            input_box = np.array(expanded_bbox)
            
            masks, scores, logits = sam_predictor.predict(
                box=input_box,
                multimask_output=False
            )
            
            if masks is not None and len(masks) > 0:
                return masks[0]
            return np.zeros_like(prev_mask)
        
        return np.zeros_like(prev_mask)
    
    def temporal_consistency(self, masks: List[np.ndarray]) -> List[np.ndarray]:
        if len(masks) < 2:
            return masks
        
        consistent_masks = [masks[0]]
        
        for i in range(1, len(masks)):
            flow = self.compute_flow(
                consistent_masks[-1], 
                masks[i]
            )
            
            propagated = self.warp_mask(consistent_masks[-1], flow)
            
            combined = cv2.bitwise_or(propagated, masks[i])
            consistent_masks.append(combined)
        
        return consistent_masks