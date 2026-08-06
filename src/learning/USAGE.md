"""
学习系统使用说明
================

本模块提供 RAG + Few-shot 学习功能，用于从人工修改中学习，提升标注质量。

目录结构
--------
src/learning/
  ├── __init__.py          # 模块初始化
  ├── config.py            # 学习配置
  ├── correction_collector.py  # 修正数据收集
  ├── vector_store.py      # 向量数据库（ChromaDB）
  ├── fewshot_manager.py   # Few-shot 示例管理
  └── run_learning.py      # 学习流程主程序

src/run_with_learning.py   # 带学习功能的标注程序（独立入口）

data/learning/
  ├── vector_db/           # ChromaDB 数据存储
  ├── corrections/         # 修正案例 JSON 文件
  └── base_examples.json   # 基础示例库


安装依赖
--------
pip install chromadb


使用方法
--------

1. 基础标注（启用学习）
----------------------
python src/run_with_learning.py --video data/test.mp4

系统会自动检索相似修正案例，将 Few-shot 示例融入提示词，生成更准确的标注。

2. 交互式修正模式
-----------------
python src/run_with_learning.py --video data/test.mp4 --interactive

标注完成后进入交互模式，可以输入修正内容，系统会自动学习。

3. 从修正文件学习
-----------------
python src/run_with_learning.py --video data/test.mp4 --learn-from correction.json

修正文件格式：
{
  "original": "原始标注内容",
  "corrected": "修正后标注内容",
  "reason": "修改原因说明"
}

4. 禁用学习功能
---------------
python src/run_with_learning.py --video data/test.mp4 --no-learning

5. 学习系统管理
---------------
# 显示统计信息
python src/learning/run_learning.py stats

# 搜索相似示例
python src/learning/run_learning.py search --query "故宫" --category "古都文化"

# 批量导入修正数据
python src/learning/run_learning.py batch --dir data/learning/corrections

# 导出训练数据
python src/learning/run_learning.py export --output training_data.json


学习流程
--------

┌─────────────────────────────────────────────────────────────┐
│  1. 模型预标注                                              │
│     ↓                                                       │
│  2. 人工修改标注                                            │
│     ↓                                                       │
│  3. 差异分析（自动识别术语修正、格式调整、内容补充等）       │
│     ↓                                                       │
│  4. 存入向量数据库（按场景分类存储）                         │
│     ↓                                                       │
│  5. 下次标注时检索相似案例，构建 Few-shot 提示词             │
└─────────────────────────────────────────────────────────────┘


差异分析类别
------------
- terminology: 术语修正（专业词汇替换）
- format: 格式调整（换行、标点、结构）
- content: 内容补充（新增信息）
- correction: 错误修正（事实性错误）


配置参数
--------
在 src/learning/config.py 中可调整：

- max_examples_per_query: 每次检索最多返回的示例数（默认 3）
- min_similarity_score: 最小相似度阈值（默认 0.6）
- scene_categories: 场景分类列表
- embedding_model: Embedding 模型


注意事项
--------
1. 本模块独立运行，不影响原有程序
2. 原程序入口：python src/run_cultural_annotation.py
3. 学习程序入口：python src/run_with_learning.py
4. 首次使用需要安装 chromadb: pip install chromadb
"""