import cv2
import numpy as np
import torch
import os
import time
from segment_anything import SamAutomaticMaskGenerator, sam_model_registry
import matplotlib.pyplot as plt

# 创建输出目录
output_dir = "/data/data/xzy/CulturalVideoAnnotation/outputs/sam_results"
os.makedirs(output_dir, exist_ok=True)

# ----------------------
# 1. 加载 SAM 模型
# ----------------------
DEVICE = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
sam = sam_model_registry["vit_b"](checkpoint="/data/data/xzy/CulturalVideoAnnotation/models/sam_vit_b_01ec64.pth").to(DEVICE)
mask_generator = SamAutomaticMaskGenerator(sam)

# ----------------------
# 2. 读取图片（换成你的鼓楼/京剧/机场图）
# ----------------------
image_path = "/data/data/xzy/CulturalVideoAnnotation/data/1.png"  # 改为指定的图片路径
image = cv2.imread(image_path)
image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

# ----------------------
# 3. SAM 自动分割
# ----------------------
masks = mask_generator.generate(image)

# ----------------------
# 4. 显示分割效果
# ----------------------
plt.figure(figsize=(12,6))
plt.subplot(1,2,1)
plt.imshow(image)
plt.title("原图")

# 合并mask
mask_image = np.zeros_like(image)
for mask in masks:
    color = np.random.rand(3)
    mask_image[mask['segmentation']] = color * 255
mask_image = mask_image.astype(np.uint8)

plt.subplot(1,2,2)
plt.imshow(mask_image)
plt.title("SAM 主体分割")

# 保存结果
timestamp = time.strftime("%Y%m%d_%H%M%S")

# 保存分割掩码
mask_output_path = os.path.join(output_dir, f"segmentation_mask_{timestamp}.png")
mask_image_bgr = cv2.cvtColor(mask_image, cv2.COLOR_RGB2BGR)
cv2.imwrite(mask_output_path, mask_image_bgr)
print(f"分割掩码已保存到: {mask_output_path}")

# 保存对比图
comparison_path = os.path.join(output_dir, f"comparison_{timestamp}.png")
plt.savefig(comparison_path, bbox_inches='tight', dpi=150)
print(f"对比图已保存到: {comparison_path}")

# 保存分割信息
info_path = os.path.join(output_dir, f"segmentation_info_{timestamp}.txt")
with open(info_path, 'w', encoding='utf-8') as f:
    f.write(f"分割时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"图像路径: {image_path}\n")
    f.write(f"分割对象数量: {len(masks)}\n")
    f.write("\n分割对象信息:\n")
    for i, mask in enumerate(masks[:10]):  # 只保存前10个对象
        f.write(f"对象 {i+1}: 面积={mask['area']}, 置信度={mask['predicted_iou']:.3f}\n")
print(f"分割信息已保存到: {info_path}")

# 显示结果（在有图形界面时）
# plt.show()