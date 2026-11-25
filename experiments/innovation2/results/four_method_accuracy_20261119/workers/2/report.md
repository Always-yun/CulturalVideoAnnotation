# 文化知识增强的文化符号标注：30视频四组实验

运行时间（北京时间）：2026-11-19T12:22:04.914749+08:00。原31条清单排除缺失的神武门，现存30条均验证4帧可读。
冻结知识库：data/knowledge_base/chinese_cultural_symbols_v2.json，114实体；参考图149条，符合启用和审核条件0条。

|方法|完成/30|实体正确|全30条准确率|运行失败|受阻|
|---|---:|---:|---:|---:|---:|
|free|9/30|3|未完成，不报告|1|0|
|text|9/30|6|未完成，不报告|1|0|
|image|0/30|0|未完成，不报告|0|10|
|multimodal|0/30|0|未完成，不报告|0|10|

## 材料与实现核查

- 已实现：视频入口scripts/run_annotation.py；InferenceEngine调用GLM/Qwen；PromptManager与emcast_schema定义EMCAST；CulturalRAGPipeline完成描述、检索、候选注入与标注。
- 文本检索为确定性关键词/别名/视觉特征匹配，不是训练的文本嵌入模型。图像检索为CLIP ViT-B/32，视频均匀4帧及实体参考图分别平均并归一化；余弦分数映射至[0,1]；融合为0.5×归一化文本分+0.5×图像分。
- v2实际114实体，v3实际126实体；默认代码使用v2，本次固定v2，不将较新版本与旧GT混用。实体字段有规范名、别名、文化维度、visual_features、spatial_features、typical_scene、cultural_description、来源与图片记录等。
- 已修复：图像检索原来忽略use_for_retrieval与verification_status；纯Image无图时仍可从文本候选池返回零分实体；并列排序不稳定。现按审核标记过滤，纯Image不混入文本候选，固定并列次序。
- 缺失材料：可用于检索的已审核真实参考图片。现存图片保留原始文件与来源，不擅自改为已审核；Image与Multimodal未满足运行条件，不能算作Text或Free的复本。
- IdentityEvidenceGate实际是确定性完整规范名/别名匹配，或visual_features片段精确匹配；OCR和参考图身份匹配标记unavailable。只有配置拒识门控后才执行。它不是知识图谱推理或训练模块。本轮四组均不启用，避免引入额外变量及旧阈值重叠问题。
- 受控生成在既有代码中是候选闭集Prompt与确定性后处理。本轮四组均controlled=False；保留实现，不增加第五组。
- 最终准确率按实际实体参考答案计算；知识库不覆盖不等于参考答案unknown。只用规范名与别名，不用keywords子串；额外错误实体也算错误。运行异常和解析失败不算拒识正确。
- 原参考答案来源含文件名和历史预测，虽标frozen，并非本轮独立双人核验；天安门/天安门广场等实体范围、人民大会堂文化类别仍有审核局限。因此本轮是既有素材上的复现实验，不能直接宣称独立泛化。
- 不设置Known/Easy Unknown/Hard Unknown分组，不训练、不新增损失函数或端到端优化；知识库覆盖仅作逐条材料记录。

## 运行与结论边界

所有标注组共用相同基础模型、生成参数与视频文件；Text使用本轮重新提取的结构化视觉观察，uncertain_entities不参与检索，未复用历史命名描述或旧预测。Prompt和模型原文、候选与关键帧均落盘。
Image/Multimodal材料未就绪时不输出准确率，不据此断言图文融合提升。完整四组结论须参考图核验并启用后补跑。

## 错误与受阻记录

- cbd2/free：预测识别出承载该文化内涵的关键视觉锚点为北京中央商务区（CBD）天际线。；参考['CBD']；entity_confusion_or_generation
- 人民大会堂/free：预测识别出承载该文化内涵的关键视觉锚点为人民大会堂、中华人民共和国国徽。；参考['人民大会堂']；entity_confusion_or_generation
- 人民英雄纪念碑1/free：C层核心符号解析失败，不能作为unknown或正确结果
- 北大1/free：预测识别出承载该文化内涵的关键视觉锚点为北京大学建筑、石狮子。；参考['北京大学']；entity_confusion_or_generation
- 北大1/text：预测识别出承载该文化内涵的关键视觉锚点为北京大学校门。；参考['北京大学']；retrieval_miss
- 天安门1/free：预测识别出承载该文化内涵的关键视觉锚点为天安门城楼、华表。；参考['天安门广场']；entity_confusion_or_generation
- 天安门1/text：预测识别出承载该文化内涵的关键视觉锚点为天安门城楼。；参考['天安门广场']；entity_confusion_or_generation
- 故宫/free：预测识别出承载该文化内涵的关键视觉锚点为太和殿、红墙黄瓦。；参考['故宫']；entity_confusion_or_generation
- 故宫/text：预测识别出承载该文化内涵的关键视觉锚点为太和殿、红墙黄琉璃瓦、中轴对称布局。；参考['故宫']；entity_confusion_or_generation
- 清华/free：预测识别出承载该文化内涵的关键视觉锚点为清华大学二校门。；参考['清华大学']；entity_confusion_or_generation
- 清华/text：Expecting ',' delimiter: line 1 column 166 (char 165)
- 全部参考图未审核且use_for_retrieval=False；需要审核并启用真实图片

复现：`python scripts/innovation2/run_four_method_accuracy.py --output-dir experiments/innovation2/results/four_method_accuracy_20261119/workers/2`；`--prepare-only`仅核查材料。已完成结果逐条保存，重启仅重试未完成项。
材料索引：manifest.json、reference_audit.json、keyframes/；运行记录：results.json、predictions.csv、summary.csv及每视频trace。
