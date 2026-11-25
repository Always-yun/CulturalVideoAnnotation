# 文化知识增强的文化符号标注：30视频四组实验

运行时间（北京时间）：2026-11-19T12:22:04.914749+08:00。原31条清单排除缺失的神武门，现存30条均验证4帧可读。
冻结知识库：data/knowledge_base/chinese_cultural_symbols_v2.json，114实体；参考图149条，符合启用和审核条件0条。

|方法|有效输出/30|实体正确|匹配率（全30条）|输出/运行失败|受阻|
|---|---:|---:|---:|---:|---:|
|free|29/30|10|33.33%|1|0|
|text|29/30|20|66.67%|1|0|
|image|0/30|0|未完成，不报告|0|30|
|multimodal|0/30|0|未完成，不报告|0|30|

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

- cbd/free：预测识别出承载该文化内涵的关键视觉锚点为中央电视台总部大楼、中国尊、国贸三期、国贸一期。；参考['CBD']；entity_confusion_or_generation
- cbd/text：预测识别出承载该文化内涵的关键视觉锚点为中国中央电视台总部大楼、中国尊、国贸中心。；参考['CBD']；retrieval_miss
- cbd3/free：预测识别出承载该文化内涵的关键视觉锚点为中国尊、国贸三期、央视总部大楼、望京SOHO。；参考['CBD']；entity_confusion_or_generation
- cbd3/text：预测识别出承载该文化内涵的关键视觉锚点为中国尊、国贸三期、央视总部大楼、望京SOHO。；参考['CBD']；retrieval_miss
- 中关村展示中心/free：预测识别出承载该文化内涵的关键视觉锚点为国家会议中心（流线型建筑）。；参考['中关村国家自主创新示范区展示中心']；entity_confusion_or_generation
- 京剧青衣/free：预测识别出承载该文化内涵的关键视觉锚点为京剧服饰、折扇。；参考['京剧']；entity_confusion_or_generation
- 京剧青衣/text：预测识别出承载该文化内涵的关键视觉锚点为京剧服饰、折扇。；参考['京剧']；retrieval_miss
- 人民大会堂/free：预测识别出承载该文化内涵的关键视觉锚点为人民大会堂、中华人民共和国国徽。；参考['人民大会堂']；entity_confusion_or_generation
- 人民英雄纪念碑/free：预测识别出承载该文化内涵的关键视觉锚点为人民英雄纪念碑、天安门广场。；参考['人民英雄纪念碑']；entity_confusion_or_generation
- 人民英雄纪念碑1/free：C层核心符号解析失败，不能作为unknown或正确结果
- 北大/free：预测识别出承载该文化内涵的关键视觉锚点为[宝塔]。；参考['北京大学']；entity_confusion_or_generation
- 北大/text：预测识别出承载该文化内涵的关键视觉锚点为[宝塔]。；参考['北京大学']；retrieval_miss
- 北大1/free：预测识别出承载该文化内涵的关键视觉锚点为北京大学建筑、石狮子。；参考['北京大学']；entity_confusion_or_generation
- 国博/free：预测识别出承载该文化内涵的关键视觉锚点为国家博物馆建筑、红色横幅、中华人民共和国国徽。；参考['中国国家博物馆']；entity_confusion_or_generation
- 天安门/free：预测识别出承载该文化内涵的关键视觉锚点为天安门城楼。；参考['天安门广场']；entity_confusion_or_generation
- 天安门/text：预测识别出承载该文化内涵的关键视觉锚点为天安门城楼、毛泽东画像、红旗。；参考['天安门广场']；retrieval_miss
- 天安门1/free：预测识别出承载该文化内涵的关键视觉锚点为天安门城楼、华表。；参考['天安门广场']；entity_confusion_or_generation
- 天安门1/text：预测识别出承载该文化内涵的关键视觉锚点为天安门城楼。；参考['天安门广场']；entity_confusion_or_generation
- 庙会/free：预测识别出承载该文化内涵的关键视觉锚点为红色灯笼、红色横幅。；参考['北京庙会']；entity_confusion_or_generation
- 庙会/text：预测识别出承载该文化内涵的关键视觉锚点为[红色灯笼、红色横幅]。；参考['北京庙会']；retrieval_miss
- 故宫/free：预测识别出承载该文化内涵的关键视觉锚点为太和殿、红墙黄瓦。；参考['故宫']；entity_confusion_or_generation
- 故宫/text：预测识别出承载该文化内涵的关键视觉锚点为太和殿、红墙黄琉璃瓦、中轴对称布局。；参考['故宫']；entity_confusion_or_generation
- 故宫全景/free：预测识别出承载该文化内涵的关键视觉锚点为故宫（紫禁城）、红墙黄瓦、飞檐斗拱。；参考['故宫']；entity_confusion_or_generation
- 未来科学城/free：预测识别出承载该文化内涵的关键视觉锚点为现代桥梁、红砖建筑群、灰色高层建筑群。；参考['未来科学城']；entity_confusion_or_generation
- 未来科学城/text：预测识别出承载该文化内涵的关键视觉锚点为现代桥梁、高层建筑群。；参考['未来科学城']；retrieval_miss
- 清华/free：预测识别出承载该文化内涵的关键视觉锚点为清华大学二校门。；参考['清华大学']；entity_confusion_or_generation
- 清华/text：Expecting ',' delimiter: line 1 column 166 (char 165)
- 角楼/free：预测识别出承载该文化内涵的关键视觉锚点为角楼、护城河、城墙。；参考['角楼']；entity_confusion_or_generation
- 角楼1/free：预测识别出承载该文化内涵的关键视觉锚点为角楼、护城河、飞檐斗拱、红墙灰瓦。；参考['角楼']；entity_confusion_or_generation
- 鸟巢/free：预测识别出承载该文化内涵的关键视觉锚点为国家体育场（鸟巢）、国家游泳中心（水立方）。；参考['鸟巢']；entity_confusion_or_generation
- 全部参考图未审核且use_for_retrieval=False；需要审核并启用真实图片

复现：`python scripts/innovation2/run_four_method_accuracy.py --output-dir experiments/innovation2/results/four_method_accuracy_20261119`；`--prepare-only`仅核查材料。已完成结果逐条保存，重启仅重试未完成项。
材料索引：manifest.json、reference_audit.json、keyframes/；运行记录：results.json、predictions.csv、summary.csv及每视频trace。

## 完成审计与解释限制

汇总完成时间（北京时间）：2026-11-19T13:05:00.210431+08:00。
共120条方法记录，120个唯一视频—方法组合；实际完成模型标注58条。
API尝试日志共95条；成功89条，失败2条，中断4条。另保留沙箱网络失败日志api_calls_restricted_network.json。没有金额数据，不估算费用。
Free→Text改善：中关村展示中心、人民大会堂、人民英雄纪念碑、人民英雄纪念碑1、北大1、国博、故宫全景、角楼、角楼1、鸟巢；退步：无。逐样本见paired_comparison.csv。
文化维度命中数（分母30）：free 23/30；text 25/30。实体与维度分别评价，不用维度正确替代具体实体正确。
Text检索诊断：有KB实体ID的27条，Top-1命中11条，Top-5命中13条；场景格式失败未检索计未召回。覆盖不足的样本仍参与30条最终实体匹配率，但没有可检索正实体，不计检索召回率。
Text候选为空：cbd3、京剧青衣、人民大会堂、天安门、庙会、未来科学城、糖葫芦、胡同、胡同1。Free/Text完全相同Prompt：cbd3、京剧青衣、人民大会堂、天安门、庙会、未来科学城、糖葫芦、胡同、胡同1；同Prompt但输出不同：人民大会堂、天安门、庙会、未来科学城。后者是重复调用差异，不能归因知识；温度0.1、单次配对仍存在采样波动。
47项回归检查通过。冻结代码、知识库和GT哈希、视频哈希及120帧哈希复核结果见final_audit.json；环境与依赖见environment.json。
计分对所有组统一去除通用显示后缀（如天际线/建筑群）及括号说明后，以完整规范名/别名核对。不同实体的名称前缀、视觉关键词和额外错误实体不给分。最初机械字符串匹配保存在literal_symbol_correct；评价代码哈希及规则见evaluation_protocol.json。此修正是在首批输出暴露格式问题后统一实施的评价实现修复，不是预注册指标；不改变模型输出或检索。
本轮主指标为C层核心实体规范化匹配率，另记录文化维度正确率；它不等于文化内涵/价值指向全部文本的人工语义准确率。后者仍缺独立人工逐条审核。
人工复核表human_review_queue.csv已生成，人工实体、维度与参考范围问题字段留空；没有把自动评分冒充人工结论。典型帧观察记录另见video_visual_spotcheck.json。
粒度差异需特别处理：如参考答案为CBD整体，而模型列出央视总部/中国尊等组成建筑，严格指标会判为未命中整体；不能仅凭这项失配断言画面中的组成建筑都是幻觉。天安门与天安门广场、校门与大学整体也存在范围问题。原GT未改写以迎合预测。
错误类型为可复核的初步诊断：retrieval_miss表示未召回目标KB ID，entity_confusion_or_generation表示候选存在时仍未匹配或Free输出失配；是否真为视觉错认、合理细粒度实体或GT范围问题，需要人工看视频判定。
单次同素材运行不证明统计显著或独立泛化；Image/Multimodal材料受阻时，不能回答完整图文融合是否提升的研究问题。
完整完成30次方法任务时，模型重复/截断而没有C层、或场景JSON解析失败的输出失败按全30条分母计为未命中，并另列失败数量；不选择性重采样该输出，不从M/E层推填C层。基础设施中断导致未观测任务时不报告完整准确率。
执行方式：固定原运行代码后用run_four_method_parallel.py对独立视频作3路调度；execution_schedule.json记录调度器哈希。workers/中的报告只是分片中间快照，以根目录report.md为正式汇总。
参考图目视抽查3例：CBD为文字封面，北大为校徽，均不是对应建筑实景；故宫为多景拼图。这些问题不能靠把启用标记改为True解决。抽查记录见reference_visual_spotcheck.json；该抽查不冒充全库人工审核。
审计缺口：冻结入口在normalize_scene之前未保存原始场景响应；清华Text的JSON解析失败原文因此不可得，只有调用元数据与异常记录。该失败不冒充未知拒识，不声称离线恢复；已新增run_four_method_with_raw_audit.py入口，后续可在新输出目录先落盘再解析；未改变本轮冻结入口或伪造缺失原文。
当前无可用CUDA驱动；本轮通过项目配置的远程GLM运行，未静默更换基础模型。
api_inputs/与api_input_manifest.json是额外准备的统一传输编码副本，本轮标注未使用；正式结果的实际输入以trace.video_path为准。
