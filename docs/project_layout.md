# 项目目录与实验索引

基础模块保留在 `src/`、`config/`、`models/`、`dataset/`；共用知识库仍位于 `data/knowledge_base/`，测试数据与原始中关村素材仍位于 `data/`。基础标注产物位于 `outputs/annotations/`、`outputs/preview/` 和 `outputs/eval/`。

## 创新点1：描述策略与文生视频评价

[实验目录](../experiments/innovation1/README.md)。任务集已从项目外移至 `experiments/innovation1/t2v_cultural_taskset/`，第一批生成视频位于 `experiments/innovation1/videos/batch1/`。第一批评价版本及第二批配置独立保留；本次只修正路径，不调整事实、提示词、评分或生成参数。

## 创新点2：文化知识增强与受控标注

[实验目录](../experiments/innovation2/README.md)。数据、运行结果、缓存与报告均位于 `experiments/innovation2/`，入口脚本位于 `scripts/innovation2/`。配置仍共用项目级 `config/`，研究文档位于 `docs/innovation2/`。

从项目根目录执行，例如：

```bash
python scripts/run_annotation.py --video data/test/鸟巢.mp4
python scripts/innovation2/run_cultural_ablation.py
python scripts/innovation2/run_identity_verifier_v2.py
```

## 历史归档与迁移记录

SAM与运镜历史文件移至 `archives/sam_camera_motion/`；这是历史快照，不代表当前实验入口。既有空目录、包标记与Git改动未清除。

[迁移清单](reorganization_20261112.json)列出每次移动和修正过的文本文件；修改前文本备份路径记录在清单中。保留了原实验文件名与版本号，未合并或删减实验产物。

## 既有数据缺口

校验发现旧GT引用的 `data/test/222.mp4` 与原 `data/实验用30个素材/神武门.mp4` 在迁移前即不存在。对应GT保留原实验语义，仅更新目录路径；未用其他视频替代。
