# 北京文化视频标注系统

基于 Qwen 3.5-9B 视觉大模型的北京城市文化视频智能标注工具，采用 EMCAST 六维分层标注体系。

## 功能特性

- 智能视频标注：基于 Qwen 3.5-9B 视觉大模型进行视频内容理解
- EMCAST 六维分层标注：
  - **E** - 场景环境层
  - **M** - 主体行为层
  - **C** - 文化维度层
  - **A** - 视听语言层
  - **S** - 整体叙事层
  - **T** - 技术属性层
- 北京文化分类：支持古都文化、红色文化、京味文化、创新文化、国际时尚文化五大类别
- 视频元数据提取：基于 ffmpeg 自动提取视频技术参数
- 批量处理：支持单个视频和批量视频标注
- 多格式输出：支持 TXT 和 JSON 格式输出

## 项目结构

```
CulturalVideoAnnotation/
├── data/                    # 视频数据目录
├── models/                  # 模型目录
├── outputs/                 # 输出结果目录
├── src/                     # 源代码目录
│   ├── __init__.py
│   ├── config.py           # 配置管理
│   ├── model_manager.py    # 模型管理
│   ├── prompt_manager.py   # 提示词管理
│   ├── video_processor.py  # 视频处理
│   ├── inference_engine.py # 推理引擎
│   ├── result_processor.py # 结果处理
│   └── run_cultural_annotation.py # 主程序
└── README.md              # 项目说明
```

## 环境要求

- Python 3.8+
- CUDA 11.8+
- PyTorch 2.0+
- ffmpeg

## 安装步骤

### 1. 创建 Conda 环境

```bash
conda create -n cultural_video python=3.10
conda activate cultural_video
```

### 2. 安装依赖

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install transformers qwen-vl-utils
pip install ffmpeg-python
pip install decord
```

### 3. 安装 ffmpeg

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# CentOS/RHEL
sudo yum install ffmpeg

# macOS
brew install ffmpeg
```

### 4. 验证安装

```bash
ffmpeg -version
python -c "import torch; print(torch.cuda.is_available())"
```

## 使用方法

### 激活环境

```bash
conda activate cultural_video
```

激活环境后会自动切换到项目目录 `/data/data/xzy/CulturalVideoAnnotation`。

#### 配置自动切换目录（可选）

如果激活环境后没有自动切换到项目目录，可以手动配置：

```bash
# 创建 conda 激活脚本
mkdir -p $CONDA_PREFIX/etc/conda/activate.d
echo 'cd /data/data/xzy/CulturalVideoAnnotation' > $CONDA_PREFIX/etc/conda/activate.d/cd_project.sh
```

这样每次激活 `cultural_video` 环境时，终端会自动切换到项目目录，可以直接运行：

```bash
python src/run_cultural_annotation.py --video data/1.mp4
```

### 单个视频标注

```bash
# 基本用法
python src/run_cultural_annotation.py --video /path/to/video.mp4
# 例如
python src/run_cultural_annotation.py --video data/1.mp4

# 指定输出文件格式
python src/run_cultural_annotation.py --video /path/to/video.mp4 --output-format txt

# 指定标注内容格式
clean 格式（只输出EMCAST六维标注）
python src/run_cultural_annotation.py --video /path/to/video.mp4 --format-type clean

# standard 格式（文件信息+EMCAST，默认）
python src/run_cultural_annotation.py --video /path/to/video.mp4 --format-type standard

# detailed 格式（完整含思考过程）
python src/run_cultural_annotation.py --video /path/to/video.mp4 --format-type detailed

# 完整参数示例
python src/run_cultural_annotation.py \
  --video /path/to/video.mp4 \
  --output-format both \
  --format-type standard \
  --fps 0.5 \
  --gpu 5 \
  --verbose
```

### 批量视频标注

```bash
# 基本用法
python src/run_cultural_annotation.py --video-dir /path/to/video/directory

# 完整参数示例
python src/run_cultural_annotation.py \
  --video-dir /path/to/video/directory \
  --output-format both \
  --fps 0.5 \
  --gpu 5 \
  --verbose
```

## 命令行参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--video` | `-v` | 指定单个视频文件路径 | - |
| `--video-dir` | `-d` | 指定视频目录（批量处理） | - |
| `--output-format` | - | 输出文件格式：txt/json/both | both |
| `--format-type` | `-t` | 标注内容格式：clean/standard/detailed | standard |
| `--output-dir` | `-o` | 指定输出目录 | ./outputs |
| `--fps` | `-f` | 视频采样帧率 | 0.5 |
| `--max-frames` | - | 最大帧数限制 | None |
| `--gpu` | - | 指定GPU设备ID | 5 |
| `--no-ffmpeg` | - | 禁用ffmpeg元数据获取 | False |
| `--verbose` | `-V` | 显示详细信息 | False |

### 格式类型说明

| 格式类型 | 文件信息 | 元数据 | EMCAST标注 | 思考过程 | 适用场景 |
|----------|----------|--------|------------|----------|----------|
| `clean` | ❌ | ❌ | ✅ 纯净 | ❌ 去除 | 快速查看标注结果 |
| `standard` | ✅ | ❌ | ✅ 纯净 | ❌ 去除 | 标准使用（默认） |
| `detailed` | ✅ | ✅ | ✅ 完整 | ✅ 保留 | 分析模型推理过程 |

## 配置说明

配置文件位于 `src/config.py`，主要配置项：

### GPU 配置
```python
@dataclass
class GPUConfig:
    device_id: int = 5              # GPU 设备 ID
    visible_devices: str = "5"       # 可见 GPU
    torch_dtype: str = "bfloat16"   # PyTorch 数据类型
```

### 模型配置
```python
@dataclass
class ModelConfig:
    model_path: str = "/path/to/Qwen3.5-9B"  # 模型路径
    trust_remote_code: bool = True             # 信任远程代码
```

### 视频配置
```python
@dataclass
class VideoConfig:
    fps: float = 0.5                    # 视频采样帧率
    max_frames: int = None               # 最大帧数
    use_ffmpeg_metadata: bool = True     # 使用 ffmpeg 获取元数据
```

### 生成配置
```python
@dataclass
class GenerationConfig:
    max_new_tokens: int = 4096          # 最大生成 token 数
    temperature: float = 0.1             # 温度参数
    top_p: float = 0.9                  # Top-p 采样
    repetition_penalty: float = 1.1       # 重复惩罚
    do_sample: bool = False              # 是否采样
```

## 输出格式

系统支持三种标注内容格式，文件名会自动包含格式类型标识：
- `1_annotation_clean_20260306_120000.txt`
- `1_annotation_standard_20260306_120000.txt`
- `1_annotation_detailed_20260306_120000.txt`

### clean 格式

只输出纯净的 EMCAST 六维标注，无文件信息，无思考过程：

```
【E｜场景环境层】
视频构建了一个北京中轴线核心区域的物理环境...

【M｜主体行为层】
画面的视觉焦点是古建筑（钟鼓楼）...

【C｜文化维度层】
该场景隶属于古都文化...

【A｜视听语言层】
镜头采用 航拍拉远（Pull Back）...

【S｜整体叙事层】
视频通过高空航拍视角...

【T｜技术属性层】
分辨率：1920x1080； 帧率：50.0 FPS； 画幅：16:9； 
动态范围：SDR； 色彩空间/像素格式：yuv420p； 采样方式：4:2:0； 
编码格式：h264； 视频时长：13.88秒
```

### standard 格式（默认）

包含文件信息和 EMCAST 六维标注，去除思考过程：

```
视频文件: 1.mp4
视频路径: data/1.mp4
标注时间: 2026-03-06 12:00:00

【E｜场景环境层】
视频构建了一个北京中轴线核心区域的物理环境...

【M｜主体行为层】
画面的视觉焦点是古建筑（钟鼓楼）...

【C｜文化维度层】
该场景隶属于古都文化...

【A｜视听语言层】
镜头采用 航拍拉远（Pull Back）...

【S｜整体叙事层】
视频通过高空航拍视角...

【T｜技术属性层】
分辨率：1920x1080； 帧率：50.0 FPS； 画幅：16:9； 
动态范围：SDR； 色彩空间/像素格式：yuv420p； 采样方式：4:2:0； 
编码格式：h264； 视频时长：13.88秒
```

### detailed 格式

包含文件信息、元数据、完整标注内容（含模型的思考过程）：

```
================================================================================
【文化特征分层标注结果】
视频文件: 1.mp4
视频路径: data/1.mp4
标注时间: 2026-03-06 12:00:00
================================================================================
【视频元数据】
  duration: 13.88
  fps: 50.0
  resolution: 1920x1080
  codec: h264
  dynamic_range: SDR
  chroma_subsampling: 4:2:0
================================================================================
【完整标注内容（含思考过程）】
用户希望我作为一名专业的北京城市文化与视听语言分析师...

<think>
**初步观察与分类：**
1.  **场景识别**：画面中心是一座古塔状建筑...
2.  **文化分类**：这明显是北京中轴线的标志性建筑...
</think>

【E｜场景环境层】
视频构建了一个北京中轴线核心区域的物理环境...
...
================================================================================
```

### JSON 格式

```json
{
  "video_path": "/path/to/2.mp4",
  "video_name": "2.mp4",
  "annotation_text": "【E｜场景环境层】...",
  "timestamp": "2026-03-05 20:47:45",
  "metadata": {
    "duration": 12.08,
    "fps": 25.0,
    "resolution": "1920x1080",
    "width": 1920,
    "height": 1080,
    "codec": "h264",
    "bitrate": "2950621",
    "aspect_ratio": "16:9",
    "pixel_format": "yuv420p",
    "dynamic_range": "SDR",
    "chroma_subsampling": "4:2:0"
  }
}
```

## 北京文化分类规则

### 古都文化
- 中轴线、皇城格局、世界遗产
- 故宫、长城、钟鼓楼等历史建筑
- 体现北京历史延续性的内容

### 红色文化
- 革命旧址、纪念设施
- 天安门广场、革命博物馆
- 国家庆典相关内容

### 京味文化
- 胡同生活、老字号
- 非遗技艺（京剧、相声、传统手工艺）
- 民俗活动相关内容

### 创新文化
- 科技园区、大兴机场
- 自动驾驶、现代文创园区
- 体现当代科技与创新气质的内容

### 国际时尚文化
- 使馆区、国际消费商圈
- 亮马河、三里屯
- 重大外交活动场所

## 常见问题

### 1. CUDA out of memory 错误

**解决方案：**
- 降低 `fps` 参数（如 `--fps 0.3`）
- 减少 `max_new_tokens` 配置
- 使用较小的 GPU 或减少批处理大小

### 2. ffmpeg 不可用

**解决方案：**
```bash
# 安装 ffmpeg
sudo apt-get install ffmpeg  # Ubuntu/Debian
sudo yum install ffmpeg      # CentOS/RHEL
brew install ffmpeg          # macOS

# 或禁用 ffmpeg 元数据获取
python src/run_cultural_annotation.py --video video.mp4 --no-ffmpeg
```

### 3. 模型加载失败

**解决方案：**
- 检查模型路径是否正确
- 确认模型文件完整性
- 检查 CUDA 版本是否兼容
- 确认 GPU 内存是否足够

### 4. 输出被截断

**解决方案：**
- 增加 `max_new_tokens` 配置（如 4096 或 8192）
- 检查视频帧数是否过多
- 降低 `fps` 参数

### 5. 视频格式不支持

**解决方案：**
- 转换视频格式为 MP4
- 确保视频编码为 H.264/H.265
- 检查视频文件是否损坏

## 技术架构

### 模块化设计

- **config.py**: 配置管理，集中管理所有配置参数
- **model_manager.py**: 模型加载和管理
- **prompt_manager.py**: 提示词模板管理
- **video_processor.py**: 视频处理和元数据提取
- **inference_engine.py**: 推理引擎，处理标注逻辑
- **result_processor.py**: 结果处理和格式化输出

### 核心流程

1. 视频验证和元数据提取
2. 视频帧采样和预处理
3. 构建 EMCAST 提示词
4. 模型推理生成标注
5. 结果提取和格式化
6. 保存输出文件

## 性能优化

### GPU 配置
- 使用 `bfloat16` 数据类型减少显存占用
- 合理设置 `CUDA_VISIBLE_DEVICES` 指定 GPU

### 视频处理
- 降低采样帧率（fps）减少输入数据量
- 限制最大帧数（max_frames）控制处理时间
- 使用 ffmpeg 元数据避免重复解析

### 推理优化
- 调整 `max_new_tokens` 平衡质量和速度
- 禁用采样（`do_sample=False`）提高确定性
- 使用 `repetition_penalty` 避免重复输出

## 许可证

本项目仅供学习和研究使用。

## 联系方式

如有问题或建议，请联系项目维护者。

## 更新日志

### v1.0.0 (2026-03-05)
- 初始版本发布
- 支持 EMCAST 六维分层标注
- 支持单个和批量视频标注
- 支持 ffmpeg 元数据提取
- 支持 TXT 和 JSON 格式输出
