"""
视频跨帧mask传播测试脚本
流程：第一帧LLM+SAM → 后续帧bbox传递+SAM重新分割
"""

import os
import cv2
import numpy as np
import torch
import json
from datetime import datetime
from typing import List
from segment_anything import sam_model_registry, SamPredictor

from src.sam.llm_sam_detector import LLM_SAM_Detector
from src.temporal.mask_propagation import MaskPropagation


def extract_frames(video_path: str, output_dir: str, max_frames: int = 50) -> List[str]:
    os.makedirs(output_dir, exist_ok=True)
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"无法打开视频: {video_path}")
    
    frames = []
    frame_idx = 0
    
    while cap.isOpened() and frame_idx < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_path = os.path.join(output_dir, f"frame_{frame_idx:04d}.png")
        cv2.imwrite(frame_path, frame)
        frames.append(frame_path)
        frame_idx += 1
    
    cap.release()
    print(f"提取了 {len(frames)} 帧")
    return frames


def visualize_frame(frame: np.ndarray, mask: np.ndarray, bbox: List[int], 
                    frame_idx: int, output_path: str):
    image = frame.copy()
    
    bbox_color = (0, 0, 255)
    mask_color = (0, 255, 0)
    text_color = (255, 255, 255)
    
    if bbox is not None:
        x1, y1, x2, y2 = bbox
        cv2.rectangle(image, (x1, y1), (x2, y2), bbox_color, 4)
    
    if mask is not None and mask.sum() > 0:
        if mask.ndim == 3:
            mask_2d = mask[0]
        else:
            mask_2d = mask
        
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
    
    cv2.putText(image, f"Frame {frame_idx}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, text_color, 3)
    
    cv2.imwrite(output_path, image)


def main():
    experiment_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    video_path = "/data/data/xzy/CulturalVideoAnnotation/data/test/017.mp4"
    if not os.path.exists(video_path):
        print(f"错误: 视频文件不存在: {video_path}")
        return
    
    base_output_dir = "/data/data/xzy/CulturalVideoAnnotation/outputs/temporal"
    experiment_dir = os.path.join(base_output_dir, experiment_id)
    frames_dir = os.path.join(experiment_dir, "frames")
    results_dir = os.path.join(experiment_dir, "results")
    os.makedirs(results_dir, exist_ok=True)
    
    frames = extract_frames(video_path, frames_dir, max_frames=30)
    
    if len(frames) == 0:
        print("错误: 未能提取视频帧")
        return
    
    print("初始化SAM模型...")
    sam_model_path = "/data/data/xzy/CulturalVideoAnnotation/models/sam_vit_b_01ec64.pth"
    sam = sam_model_registry["vit_b"](checkpoint=sam_model_path)
    sam.to(device="cuda" if torch.cuda.is_available() else "cpu")
    sam_predictor = SamPredictor(sam)
    
    print("初始化LLM_SAM_Detector...")
    detector = LLM_SAM_Detector(sam_model_path=sam_model_path)
    
    print("初始化MaskPropagation...")
    propagator = MaskPropagation(method="bbox_transfer")
    
    results = []
    
    print("\n处理第0帧（LLM+SAM）...")
    first_frame_path = frames[0]
    first_frame = cv2.imread(first_frame_path)
    
    detection_result = detector.detect(first_frame_path)
    if detection_result and detection_result.get('results'):
        first_result = detection_result['results'][0]
        current_mask = first_result['mask']
        current_bbox = first_result['scaled_bbox']
        
        visualize_frame(first_frame, current_mask, current_bbox, 0, 
                       os.path.join(results_dir, f"result_0000.png"))
        
        results.append({
            'frame': 0,
            'method': 'llm_sam',
            'bbox': current_bbox,
            'mask_area': int(current_mask.sum()) if current_mask is not None else 0
        })
        print(f"  第0帧: mask面积={results[-1]['mask_area']}")
    else:
        print("  第0帧检测失败，退出")
        return
    
    for frame_idx in range(1, len(frames)):
        print(f"处理第{frame_idx}帧（bbox传递+SAM）...")
        
        frame_path = frames[frame_idx]
        current_frame = cv2.imread(frame_path)
        
        propagated_mask = propagator.propagate(
            prev_frame=cv2.imread(frames[frame_idx-1]),
            curr_frame=current_frame,
            prev_mask=current_mask,
            sam_predictor=sam_predictor
        )
        
        current_mask = propagated_mask
        current_bbox = propagator.get_mask_bbox(current_mask)
        
        visualize_frame(current_frame, current_mask, current_bbox, frame_idx,
                       os.path.join(results_dir, f"result_{frame_idx:04d}.png"))
        
        results.append({
            'frame': frame_idx,
            'method': 'bbox_transfer',
            'bbox': current_bbox,
            'mask_area': int(current_mask.sum()) if current_mask is not None else 0
        })
        print(f"  第{frame_idx}帧: mask面积={results[-1]['mask_area']}")
    
    result_json = os.path.join(experiment_dir, "results.json")
    with open(result_json, "w", encoding="utf-8") as f:
        json.dump({
            "experiment_id": experiment_id,
            "video_path": video_path,
            "total_frames": len(frames),
            "timestamp": datetime.now().isoformat(),
            "results": results
        }, f, indent=2, ensure_ascii=False)
    
    print("\n合成可视化视频...")
    result_video_path = os.path.join(experiment_dir, "propagation_result.mp4")
    
    first_result = cv2.imread(os.path.join(results_dir, "result_0000.png"))
    h, w = first_result.shape[:2]
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_writer = cv2.VideoWriter(result_video_path, fourcc, 10.0, (w, h))
    
    for frame_idx in range(len(frames)):
        result_path = os.path.join(results_dir, f"result_{frame_idx:04d}.png")
        result_frame = cv2.imread(result_path)
        video_writer.write(result_frame)
    
    video_writer.release()
    
    print(f"\n结果保存在: {experiment_dir}")
    print(f"可视化视频: {result_video_path}")


if __name__ == "__main__":
    main()