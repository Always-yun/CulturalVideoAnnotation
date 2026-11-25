# EMCAST - 中华文化视频结构化标注框架

面向中华文化视频的多模态文化符号知识库驱动标注框架（北京为当前实验案例），采用 **EMCAST 六维分层标注体系**。

## 功能特性

- **智能视频标注**：基于 Qwen 3.5-9B 视觉大模型进行视频内容理解
- **EMCAST 六维分层标注**：
  - **E** - 场景环境层
  - **M** - 主体行为层
  - **C** - 文化维度层
  - **A** - 视听语言层
  - **S** - 整体叙事层
  - **T** - 技术属性层
- **中华文化五维分类（创新点2）**：古城与历史文化、红色文化、民族与民俗文化、科技与创新文化、现代城市与国际文化；由中华文化符号知识库经"多模态检索 → Top-K 文化候选 → 动态 Prompt"驱动受控标注（北京为当前地域实验案例）
- **视频元数据提取**：基于 ffmpeg 自动提取视频技术参数
- **批量处理**：支持单个视频和批量视频标注
- **多格式输出**：支持 TXT 和 JSON 格式输出
- **多GPU并行处理**：智能检测GPU状态，自动分配任务到空闲GPU
- **实验评估系统**：支持 Baseline 对比实验、消融实验，自动计算各项指标

## 项目结构

```text
CulturalVideoAnnotation/
├── src/                         # 共用源码：标注、模型接口、文化检索、指标
├── scripts/                     # 基础标注入口、知识库维护
│   └── innovation2/             # 创新点2实验入口（从项目根目录运行）
├── config/                      # 共用策略与版本化门控配置
├── models/                      # 模型权重
├── dataset/                     # 通用数据转换
├── data/                        # 共用数据：knowledge_base、test、test_samples、中关村、eval
├── outputs/                     # 基础标注输出：annotations、preview、eval
├── experiments/
│   ├── innovation1/             # EMCAST描述策略与文化视频生成评价
│   │   ├── t2v_cultural_taskset/ # 候选任务、第一批评价、第二批配置及提示词
│   │   └── videos/batch1/       # 第一批生成视频
│   └── innovation2/             # 文化知识增强、检索、拒识与身份门控
│       ├── data/                # 实验视频、GT、人工标注导出
│       ├── runs/                # 消融实验逐次运行产物
│       ├── cache/               # 场景描述、关键帧、验证信号
│       ├── outputs/             # 文化RAG中间输出
│       ├── results/             # 指标汇总与分析
│       └── reports/             # HTML等报告
├── archives/sam_camera_motion/  # 历史SAM与运镜模块
├── docs/                        # 研究文档、目录说明和迁移清单
└── README.md
```

目录使用说明见 [docs/project_layout.md](docs/project_layout.md)。实验入口均从项目根目录运行；创新点1原项目外任务集已完整迁入。

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
pip install ffmpeg-python decord
pip install pandas numpy scipy scikit-learn nltk
pip install rouge-score  # ROUGE指标
pip install pycocoevalcap  # BLEU/CIDEr指标（可选）
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

```bash
mkdir -p $CONDA_PREFIX/etc/conda/activate.d
echo 'cd /data/data/xzy/CulturalVideoAnnotation' > $CONDA_PREFIX/etc/conda/activate.d/cd_project.sh
```

### 结构化视觉证据与文字复核

Pass-1默认输出结构化主体、外观与文字区域证据；发现匾额/标牌时按需裁剪真实视频帧并复核文字。每视频最多增加3次GLM调用。`--no-text-recognition`关闭额外转录，`--scene-mode legacy`使用旧版Pass-1。详细过程、限制和验证见 [第一步优化记录](docs/innovation2/scene_evidence_v1_20261112.md)。

### 候选排序实验版本

`--retrieval-strategy evidence_v1`启用名称/清楚文字优先、通用特征降权及文本图像双路候选合并。默认保留legacy，待独立验证与门控重新标定后再决定切换。配对回放与限制见[第二步优化记录](docs/innovation2/evidence_ranking_v1_20261112.md)。

### 默认文化增强流程

`run_annotation.py` 默认使用创新点2的完整文化链路：视频视觉描述 → 关键词与CLIP多模态Top-K检索 → 拒识门控 → EMCAST受控标注 → v2文化身份核验。复用现有v2知识库与标定配置；可通过 `--kb-path` 指定其他知识库版本。T层由视频元数据确定性写入。

```bash
# 完整流程，输出TXT/JSON及文化检索与核验追踪
python scripts/run_annotation.py --video data/test/鸟巢.mp4

# 原始EMCAST对照，不调用文化检索与核验
python scripts/run_annotation.py --video data/test/鸟巢.mp4 --culture-mode off

# 轻量关键词检索，保留拒识门控，关闭v2视觉身份核验
python scripts/run_annotation.py --video data/test/鸟巢.mp4 --culture-mode keyword --identity-verifier off
```

默认结果位于 `outputs/annotations/`，文化过程记录位于输出目录内的 `cultural_traces/`；含视觉描述、候选与分项分数、提示词、原始标注、最终C层和v2核验。单个视频会有两次基础VLM调用，模糊身份可能触发额外核验。CLIP首次使用需要本地权重或下载；`--max-frames` 控制本地Qwen抽帧，不控制GLM整视频API。多GPU入口支持相同文化参数。

### 单个视频标注

```bash
# 基本用法
python scripts/run_annotation.py --video data/test/鸟巢.mp4

# 指定输出文件格式
python scripts/run_annotation.py --video /path/to/video.mp4 --output-format txt

# 指定标注内容格式
# clean 格式（只输出EMCAST六维标注）
python scripts/run_annotation.py --video /path/to/video.mp4 --format-type clean

# standard 格式（文件信息+EMCAST，默认）
python scripts/run_annotation.py --video /path/to/video.mp4 --format-type standard

# detailed 格式（完整含思考过程）
python scripts/run_annotation.py --video /path/to/video.mp4 --format-type detailed

# 完整参数示例
python scripts/run_annotation.py \
  --video /path/to/video.mp4 \
  --output-format both \
  --format-type standard \
  --fps 0.5 \
  --gpu 5 \
  --verbose
```

### 批量视频标注

```bash
python scripts/run_annotation.py --video-dir /path/to/video/directory

# 完整参数示例
python scripts/run_annotation.py \
  --video-dir /path/to/video/directory \
  --output-format both \
  --fps 0.5 \
  --gpu 5 \
  --verbose
```

### 多GPU并行处理（推荐）

```bash
# 检查GPU状态（不执行任务）
python scripts/run_multi_gpu.py --check-gpu-only

# 处理单个视频（自动选择最佳GPU）
python scripts/run_multi_gpu.py --video /path/to/video.mp4

# 处理多个视频（自动分配到多个GPU）
python scripts/run_multi_gpu.py --video video1.mp4 video2.mp4 video3.mp4

# 处理整个目录的视频（自动分配到多个GPU并行处理）
python scripts/run_multi_gpu.py --video-dir /path/to/video/directory

# 指定使用的GPU列表（默认检测GPU 0-4）
python scripts/run_multi_gpu.py --video-dir /path/to/video/directory --gpu-ids 0 1 2 3 4

# 完整参数示例
python scripts/run_multi_gpu.py \
  --video-dir /path/to/video/directory \
  --gpu-ids 0 1 2 3 4 \
  --videos-per-gpu 1 \
  --output-format both \
  --format-type standard \
  --fps 0.5 \
  --verbose
```

### 实验评估

```bash
# 生成测试数据
python -m metrics.generate_test_data

# 运行 Baseline 对比评估
python -m metrics.baseline_eval \
  --data data/eval/test_data.jsonl \
  --output outputs/eval

# 使用自定义评估数据
# 数据格式（JSONL）：每条包含 video_id, gt_emcast, gpt_output, prompt_output, emcast_output
python -m metrics.baseline_eval \
  --data your_eval_data.jsonl \
  --output outputs/eval
```

### 创新点2 消融实验（五模式对比）

```bash
# 默认：GT 全部视频 × 全部 5 种模式（free / text / image / multimodal / multimodal_controlled）
python scripts/innovation2/run_cultural_ablation.py

# 仅指定模式与视频
python scripts/innovation2/run_cultural_ablation.py --modes free,multimodal --video-ids niaochao

# 自定义候选数与融合权重
python scripts/innovation2/run_cultural_ablation.py --top-k 5 --fusion-alpha 0.5
```

五种模式：Free Prompt（无检索）、关键词检索、图像检索（纯 image_score）、
多模态融合（text+image 加权）、多模态+受控输出（候选闭集约束）。

统一记录 Top-K 候选（text_score / image_score / fusion_score）、最终文化符号、
最终文化维度、unknown_symbol、模型输出全文。

输出（`experiments/innovation2/runs/cultural_ablation/<时间戳>/`）：
- `results.json` — 全量记录（含 Prompt 与模型输出）
- `per_video.csv` — 逐视频逐模式明细（含符号命中/幻觉/拒识标记，`human_edit` 列预留人工审核）
- `summary.csv` — 模式×指标汇总（Recall@1/5、MRR、符号/维度准确率、幻觉率、unknown拒识率、人工修改率）
- 每视频每模式中间产物（视觉描述 / Query / 候选 / Prompt / 最终标注）

评测集：`experiments/innovation2/data/eval/cultural_ablation_gt.jsonl`（video_id、gt_symbol_ids、gt_symbols、gt_dimension_code、notes）。扩大数据集时按该格式追加行即可。

## 命令行参数

### 标注程序（run_annotation.py）

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

### 多GPU模式（run_multi_gpu.py）

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--video` | `-v` | 指定视频文件路径（可多个） | - |
| `--video-dir` | `-d` | 指定视频目录 | - |
| `--gpu-ids` | - | 指定要使用的GPU ID列表 | 0 1 2 3 4 |
| `--videos-per-gpu` | - | 每个GPU处理的视频数量 | 1 |
| `--output-dir` | `-o` | 指定输出目录 | ./outputs |
| `--output-format` | - | 输出文件格式：txt/json/both | both |
| `--format-type` | `-t` | 标注内容格式：clean/standard/detailed | standard |
| `--fps` | `-f` | 视频采样帧率 | 0.5 |
| `--max-frames` | - | 最大帧数限制 | None |
| `--verbose` | `-V` | 显示详细信息 | False |
| `--check-gpu-only` | - | 仅检查GPU状态，不执行任务 | False |

### 格式类型说明

| 格式类型 | 文件信息 | 元数据 | EMCAST标注 | 思考过程 | 适用场景 |
|----------|----------|--------|------------|----------|----------|
| `clean` | ❌ | ❌ | ✅ 纯净 | ❌ 去除 | 快速查看标注结果 |
| `standard` | ✅ | ❌ | ✅ 纯净 | ❌ 去除 | 标准使用（默认） |
| `detailed` | ✅ | ✅ | ✅ 完整 | ✅ 保留 | 分析模型推理过程 |

## 配置说明

配置文件位于 `models/config.py`，主要配置项：

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

### EMCAST 标准格式

```
【E｜场景环境层】：视频构建了一个北京中轴线核心区域的物理环境...

【M｜主体行为层】：视觉焦点包含承载主体：钟鼓楼
承载主体外观：钟鼓楼呈现出轴对称的几何形态，外立面材质主要为青砖灰瓦...

【C｜文化维度层】：该场景隶属于古城与历史文化。
核心符号：识别出承载该文化内涵的关键视觉锚点为飞檐斗拱、青砖灰瓦、钟鼓楼。

【A｜视听语言层】
镜头语法：镜头为运动机位。运镜采用拉（后），状态稳定，节奏慢...

【S｜整体叙事层】：视频通过高空航拍视角...

【T｜技术属性层】
分辨率：1920x1080；帧率：25 FPS；画幅：16:9；动态范围：SDR...
```

### JSON 格式

```json
{
  "video_path": "/path/to/video.mp4",
  "video_name": "video.mp4",
  "annotation_text": "【E｜场景环境层】...",
  "timestamp": "2026-03-06 12:00:00",
  "metadata": {
    "duration": 13.88,
    "fps": 25.0,
    "resolution": "1920x1080",
    "codec": "h264"
  }
}
```

### 评估结果格式

评估输出包含三个文件：
- `result.csv`：详细评估结果（每样本一行）
- `result_summary.csv`：汇总统计（均值+标准差）
- `result_summary.md`：Markdown格式的对比表格（可直接用于论文）

## 中华文化五维分类规则（C 文化维度层）

五维分类受控于中华文化符号知识库（`data/knowledge_base/chinese_cultural_symbols_v2.json`，
当前 114 条，`culture_scope=中华文化`）。
标注时由"多模态检索 → Top-K 文化候选 → 动态 Prompt"给出候选，最终须结合画面证据闭集判定。

### 古城与历史文化（ANCIENT）
- 古城中轴线、皇城格局、世界遗产
- 故宫、长城、天坛、钟鼓楼等历史建筑与古遗址
- 体现历史延续性与传统营造技艺的内容

### 红色文化（RED）
- 革命旧址、纪念设施
- 天安门广场、革命/军事博物馆、卢沟桥
- 国家庆典与革命历史相关内容

### 民族与民俗文化（FOLK）
- 胡同、四合院等传统民居与市井生活
- 非遗技艺（京剧、京韵大鼓、剪纸、传统手工艺）
- 节庆民俗、地方美食与老字号相关内容

### 科技与创新文化（TECH）
- 科技园区与高教机构（中关村、北大、清华）
- 现代科技地标（鸟巢、水立方、国家会议中心）
- 自动驾驶、人工智能等当代科技创新内容

### 现代城市与国际文化（MODERN）
- 中央商务区、国际消费商圈（CBD、三里屯、王府井）
- 现代艺术与文创园区（798、郎园、北京坊、首钢园）
- 使馆区、重大国际交往活动场所

> 维度码与旧→新维度映射详见 `data/knowledge_base/schema.json`；
> 历史标注中的旧五维名（古都文化/京味文化/创新科技文化/国际时尚文化）
> 会由 `normalize_cultural_category()` 自动归一化，评测可直接兼容旧真值。

## 常见问题

### 1. CUDA out of memory 错误

**解决方案：**
- 降低 `fps` 参数（如 `--fps 0.3`）
- 减少 `max_new_tokens` 配置
- 使用较小的 GPU 或减少批处理大小

### 2. ffmpeg 不可用

**解决方案：**
```bash
sudo apt-get install ffmpeg
# 或禁用 ffmpeg 元数据获取
python scripts/run_annotation.py --video video.mp4 --no-ffmpeg
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

### 5. 评估指标报错

**解决方案：**
- 确保安装了必要依赖：`pip install nltk rouge-score pycocoevalcap`
- 检查评估数据格式是否正确

## 技术架构

### 模块化设计

```
pipeline/
├── inference_engine.py   # 推理引擎，处理标注逻辑
├── prompt_manager.py     # 提示词模板管理（EMCAST六维分层）
├── result_processor.py   # 结果处理和格式化输出
└── video_processor.py    # 视频处理和元数据提取

models/
├── config.py             # 配置管理，集中管理所有配置参数
├── model_manager.py      # 模型加载和管理（Qwen/GLM-4）
└── gpu_manager.py        # GPU状态检测和智能任务分配

metrics/
├── emcast_schema.py      # EMCAST Schema定义（六层结构、受控词表）
├── cultural_metrics.py   # 文化符号指标（P/R/F1、结构准确率）
├── text_metrics.py       # 文本生成指标（BLEU、CIDEr、ROUGE）
└── baseline_eval.py      # Baseline对比实验评估器
```

### 核心流程

1. 视频验证和元数据提取
2. 视频帧采样和预处理
3. 构建 EMCAST 提示词（含受控词表约束）
4. 模型推理生成标注
5. 结果提取和格式化
6. 保存输出文件

## 性能优化

- 使用 `bfloat16` 数据类型减少显存占用
- 降低采样帧率（fps）减少输入数据量
- 限制最大帧数（max_frames）控制处理时间
- 禁用采样（`do_sample=False`）提高确定性
- 多GPU并行处理最大化利用资源

## 许可证

本项目仅供学习和研究使用。

## 更新日志

### v1.5.0 (2026-09-07)
- **RealEstate10K 运镜对比实验子集与运镜真值标注模块**（已归档至 `archives/sam_camera_motion/`）：
  - 原 `src/temporal/` 运镜模块 + `data/realestate10k_subset/` 数据，因当前实验未使用该特性而整体归档
- **项目文件整理**：模型权重/对比图/散落标注结果归位，清理 9.4GB 重复实验产物

### v1.4.0 (2026-07-02)
- **代码清理与重构**：
  - 删除 `src/` 目录下所有存根文件（实际代码已迁移至 `pipeline/`）
  - 删除根目录兼容性 shim 文件（`run_multi_gpu.py`, `txt-to-json.py`）
  - 删除旧测试文件（`test_sam.py`, `test_sam_auto.py`）
- **SAM 建筑检测**（已归档至 `archives/sam_camera_motion/`）：原 `src/sam/` 模块与相关脚本，因当前实验未使用该特性而整体归档
- **项目结构优化**：精简目录结构，核心代码集中在 `pipeline/`、`models/`、`scripts/`

### v1.3.0 (2026-06-30)
- **代码结构重构**：模块化分层设计
  - 新增 `pipeline/` 目录：标注/推理系统
  - 新增 `models/` 目录：模型封装
  - 新增 `dataset/` 目录：数据处理
  - 新增 `metrics/` 目录：评价指标体系
  - 新增 `scripts/` 目录：执行脚本
- **实验评估系统**：
  - 实现 `metrics/emcast_schema.py`：EMCAST Schema定义和受控词表
  - 实现 `metrics/cultural_metrics.py`：文化符号P/R/F1、结构准确率
  - 实现 `metrics/text_metrics.py`：BLEU-1~4、CIDEr、ROUGE-1/2/L
  - 实现 `metrics/baseline_eval.py`：Baseline对比实验评估器
  - 支持 JSONL/CSV 输入，输出 CSV + Markdown 表格

### v1.2.0 (2026-06-15)
- **RAG + Few-shot 学习系统**（已移除）：
  - 原 `src/learning/` 模块（修正案例收集/向量检索/Few-shot 增强），后续因实验一二未使用该特性而整体下线

### v1.1.0 (2026-05-08)
- **多GPU并行处理**：
  - 新增 `gpu_manager.py` 模块，支持GPU状态检测和智能任务分配
  - 新增 `run_multi_gpu.py` 脚本，支持多GPU并行视频标注
- 优化GPU可用性评分算法（综合考虑内存、利用率和进程数）

### v1.0.0 (2026-03-05)
- 初始版本发布
- 支持 EMCAST 六维分层标注
- 支持单个和批量视频标注
- 支持 ffmpeg 元数据提取
- 支持 TXT 和 JSON 格式输出
