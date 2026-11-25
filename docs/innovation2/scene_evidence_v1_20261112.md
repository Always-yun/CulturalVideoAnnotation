# 第一步：结构化视觉描述与按需文字复核

2026-11-12完成。当前主入口默认使用structured_v1；本次未修改检索融合权重、门控阈值、知识库或GT，也未重跑31条正式实验。

## 行为

Pass-1输出scene、subject、visible_features、background、readable_text、text_regions和uncertain_entities。背景和身份猜测保留在审计记录中，不直接作为主体身份检索文本；仅清楚且不含缺字占位符的文字进入检索。

Pass-1报告文字区域及其出现时刻后，按time_ratio读取真实视频帧，按归一化bbox裁剪并稍扩边缘，保存裁剪图和整帧上下文，用GLM多图输入逐字复核。每视频最多3个区域、3次额外调用，无区域则0次。这里是VLM定位与视觉文字转录，没有引入独立OCR检测/识别模型。legibility是模型报告的可辨认程度，不是经过校准的正确率。

一旦进行了文字复核，检索文字使用复核结果替代Pass-1初读文字，避免互相矛盾的名称共同进入检索；模糊、失败结果保留原文与错误原因，不补字。局部裁剪不做生成式图像增强。当前局部文字复核支持GLM后端；本地Qwen记录unsupported_backend，仍可使用结构化Pass-1证据。

过程保存在文化trace、`00_scene_evidence.json`及`text_evidence/`，包含原始响应、结构化证据、实际检索文本、裁剪坐标、帧号、图片路径、转录结果和调用数。新结构化响应解析失败时按证据不足处理；历史纯文本缓存可继续使用并标记legacy_cache，不能视为新方法已处理。

## 使用

```bash
# 主入口默认结构化描述及按需文字复核
python scripts/run_annotation.py --video experiments/innovation2/data/videos/北大1.mp4

# 结构化描述但关闭额外文字识别（消融）
python scripts/run_annotation.py --video experiments/innovation2/data/videos/北大1.mp4 --no-text-recognition

# 旧版Pass-1对照
python scripts/run_annotation.py --video experiments/innovation2/data/videos/北大1.mp4 --scene-mode legacy

# 只检查第一步证据与现有检索，不运行最终标注
python scripts/innovation2/inspect_scene_evidence.py --video experiments/innovation2/data/videos/北大1.mp4 --output-dir experiments/innovation2/outputs/scene_evidence_v1/beida1_new
```

多GPU入口同样透传scene-mode及no-text-recognition。独立CulturalRAGPipeline调用可用scene_mode与text_recognition参数控制。

## 验证

14项回归测试通过，包含真实合成视频的坐标裁剪/时刻取帧、多图请求、无区域零调用、无效区域过滤、模糊与猜测信息隔离、复核覆盖初读、历史缓存兼容、异常格式降级、证据保存，以及原有六维标注与门控测试。源码编译检查通过。

北大1开发诊断：结构化Pass-1定位到匾额，但没有直接读出文字；一次局部复核读出“北京大学”，裁剪图已查看确认。未改动检索权重时，历史Top-1“卢沟桥”、正确对象不在Top-5，变为新Top-1“北京大学”（fusion=0.8561）。本次第一步与检索耗时106.34秒，其中额外文字复核1次。

该样本已用于错误诊断；新旧记录不是严格控制采样的配对消融，不能据此推算总体准确率提升，也未验证最终C层自动接受。下一步应冻结此版本后，在独立开发/验证样本上比较旧Pass-1、仅结构化、结构化+文字复核，并记录召回、误识别与额外调用成本。

[真实诊断记录](../../experiments/innovation2/outputs/scene_evidence_v1/beida1/scene_evidence_report.json)；[历史对比](../../experiments/innovation2/outputs/scene_evidence_v1/beida1/comparison.json)。
