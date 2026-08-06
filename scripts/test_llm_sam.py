"""
LLM+SAM 检测测试脚本
使用新的 sam 模块和标准化的数据集结构
"""

import os
import json
from datetime import datetime
from src.sam.llm_sam_detector import LLM_SAM_Detector


def main():
    experiment_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    detector = LLM_SAM_Detector()
    
    output_dir = os.path.join("/data/data/xzy/CulturalVideoAnnotation/outputs/sam", experiment_id)
    os.makedirs(output_dir, exist_ok=True)
    
    test_images = [
        ("钟鼓楼.png", "钟鼓楼"),
        ("zgc.png", "中关村"),
        ("水倒影.png", "水倒影"),
    ]
    
    data_dir = "/data/data/xzy/CulturalVideoAnnotation/data/test_samples"
    
    results = []
    for img_name, desc in test_images:
        img_path = os.path.join(data_dir, img_name)
        if not os.path.exists(img_path):
            print(f"警告: 图片不存在: {img_path}")
            continue
        
        result = detector.detect(img_path)
        if result:
            output_path = os.path.join(output_dir, f"{desc}_detection.png")
            detector.visualize(result, output_path)
            
            result_info = {
                "image": img_name,
                "description": desc,
                "num_objects": len(result.get("results", [])),
                "output_path": output_path
            }
            results.append(result_info)
            
            print(f"处理完成: {desc}")
    
    result_json = os.path.join(output_dir, "results.json")
    with open(result_json, "w", encoding="utf-8") as f:
        json.dump({
            "experiment_id": experiment_id,
            "timestamp": datetime.now().isoformat(),
            "results": results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n结果保存在: {output_dir}")


if __name__ == "__main__":
    main()