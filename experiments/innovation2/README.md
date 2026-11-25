# 创新点2：文化知识增强与受控标注

## 2026-11-19：Image/Multimodal C层补充运行（当前结果）

Image、Multimodal各30条已完成，60条原始回复均保存并解析。Free/Text未重跑，提取历史六维输出的C层，按本轮明确的主要实体与严格附加实体规则重新评分。用户已确认全部30条主要实体及文化类别，指标按已确认参考计算；旧六维提示和114实体库与新C-only提示、126实体库存在可比性限制。

- [完整报告与全部交付索引](results/image_multimodal_c_20261119/report.md)
- [实际成功与失败案例](results/image_multimodal_c_20261119/case_analysis.md)
- [逐视频评价明细](results/image_multimodal_c_20261119/per_video_evaluation.csv)
- [已确认参考答案表](results/image_multimodal_c_20261119/reference_answers_confirmed.csv)

独立13张实拍开发图留出，冻结alpha=0.5、Top-K=3、阈值=0；Image主要实体命中23/30，Multimodal24/30，仅差故宫一条，涉及建筑群/单体层级，不能据此声称普遍优势。参数未按测试结果调整。以下段落为历史运行记录。

## 2026-11-19：既有30视频四组实验核查与运行

按确认的现存30条视频运行同一GLM基础模型。C层核心实体规范化匹配：Free 10/30（33.33%），Text 20/30（66.67%）；各有1条格式/输出失败，保留在30条分母中。47项回归检查通过。

Image与Multimodal因参考图全部未审核且禁用而未运行标注；抽查发现文字封面、校徽和多景拼图。当前不能据此判断图文融合收益。Text部分样本无候选、与Free使用相同Prompt，其采样差异不能归因知识；原参考答案仍需独立人工审核。本轮不采用Known/Easy/Hard Unknown分组，不新增训练。

- [本轮材料清单、实际结果、错误与限制](results/four_method_accuracy_20261119/report.md)
- [逐视频Free/Text配对](results/four_method_accuracy_20261119/paired_comparison.csv)
- [人工复核表（人工判断留空）](results/four_method_accuracy_20261119/human_review_queue.csv)


## 最新开发结果（2026-11-12）

联合召回＋独立视频核验H3已完成20/20：严格准确率18/20=90%，同批A基线14/20=70%；Known 16/18，Unknown拒识2/2。仅为开发结果，不作为独立测试结论。

- [完整结果与逐样本对照](results/hybrid_accuracy_v3_complete/report.md)
- [方法、格式恢复与复现记录](../../docs/innovation2/hybrid_accuracy_v3_20261112.md)
- [上轮无净提升的修复实验](results/accuracy_repair_v2/report.md)


- `data/videos/`：正式实验素材；`data/eval/`：GT及拒识阈值；`data/cultural_eval/`：人工事实表；`data/label_studio_exports/`：原始标注导出。
- `runs/cultural_ablation/`：按既有运行名、版本保存的消融实验。
- `cache/`：场景描述、关键帧与拒识验证信号。
- `outputs/cultural_rag/`：文化RAG过程输出。
- `results/cultural_rag/`：final30、final31、unknown_analysis、identity_gate等汇总。
- `reports/`：可查看报告。

从项目根目录运行 `scripts/innovation2/` 下入口；共用知识库为 `data/knowledge_base/`，门控策略为 `config/`。研究说明见 `docs/innovation2/`。所有路径均已随迁移同步修正。
