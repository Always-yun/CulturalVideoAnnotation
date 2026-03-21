import torch
import cv2
import os

# 1. 明确指定使用 GPU 5（目前最空的那张）
os.environ["CUDA_VISIBLE_DEVICES"] = "5"

def check_env():
    print(f"当前使用的显卡: {torch.cuda.get_device_name(0)}")
    
    # 模拟创建一个张量并搬到显卡上
    x = torch.rand(100, 100).cuda()
    print("显卡计算测试成功！")

def test_load_video(video_path):
    # 这里填入你北京台素材的路径
    if not os.path.exists(video_path):
        print(f"错误：找不到文件 {video_path}")
        return

    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    if ret:
        print(f"成功读取视频！分辨率为: {frame.shape[1]}x{frame.shape[0]}")
        # 保存第一帧，用于后续你的“文化特征”标注实验
        cv2.imwrite("first_frame_test.jpg", frame)
        print("已提取首帧图像：first_frame_test.jpg")
    else:
        print("无法读取视频帧，请检查解码器。")
    cap.release()

if __name__ == "__main__":
    check_env()
    
    # 【这里就是填路径的地方】
    video_to_test = "/data/data/xzy/1.mp4" 
    
    test_load_video(video_to_test)