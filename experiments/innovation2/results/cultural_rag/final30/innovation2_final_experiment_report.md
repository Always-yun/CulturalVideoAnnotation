# 创新点2 正式实验报告：知识增强多模态检索 + 身份证据拒识门控

> 全部数字由 `scripts/innovation2/analyze_final30.py` 从冻结 GT 与落盘实验结果自动计算，无手工填值。


## 1. 实验设置

- 数据集：`experiments/innovation2/data/videos/` 中 31 条人工核验文化视频（30 个素材 + 1 条同场景重复拍摄），GT 冻结于 `experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl`，人审表见 `experiments/innovation2/data/cultural_eval/cultural_eval_30.csv`，`review_status=frozen`。
- 样本类型分布：Known 27 / Easy Unknown 1 / Hard Unknown 3。
- 知识库：v2 正式 KB 共 114 个文化符号，参考图覆盖 88/114 个符号；31 条视频中的 Known 样本有 24/27 条其 GT 符号具备可用真实参考图。
- 五维分布（样本 / KB）：ANCIENT 8 / 40，RED 5 / 12，FOLK 6 / 12，TECH 8 / 28，MODERN 4 / 10。
- 模型与参数：标注模型 GLM-4V（API），图像编码器 CLIP ViT-B/32；统一 `top_k=5`、关键帧采样 `num_frames=4`、Pass-1 场景描述在同批视频内跨模式复用。
- 融合权重：`fusion_score = α·text_score + (1-α)·image_score`，α=0.5（Text+Image 融合，取自既有配置，未在 test 集上调）；Image 模式 α=0（纯图像分），Text 模式纯文本不进融合。
- 图像证据：Image / Multimodal 的图像分严格来自「视频关键帧 CLIP embedding」与「KB 真实参考图 CLIP embedding」的余弦相似度；无真实参考图的符号不参与图像排序（图像分缺失），在逐条明细中标记 `image_evidence_status=unavailable`，不使用文本描述模拟图像检索。
- Gate 阈值：来自验证集网格搜索产物 `experiments/innovation2/data/eval/rejection_thresholds.json`（v2-30sucai：text score_thr=0.5，image/multimodal score_thr=0.4，margin_thr=0，require_keywords=true），未在 test 集调整。Identity Evidence Gate 配置为 `config/identity_evidence_gate.json`，其强证据仅接受 canonical/alias 完整实体命中或 KB 独特视觉属性命中。

### 1.1 每个文化符号的样本数

| 文化符号 | 样本数 |
|---|---|
| CBD | 4 |
| 人民大会堂 | 2 |
| 人民英雄纪念碑 | 2 |
| 北京大学 | 2 |
| 天安门广场 | 2 |
| 故宫 | 2 |
| 胡同 | 2 |
| 角楼 | 2 |
| 中关村壹号 | 1 |
| 中关村国际创新中心 | 1 |
| 中关村国家自主创新示范区展示中心 | 1 |
| 京剧 | 1 |
| 兔儿爷 | 1 |
| 中国国家博物馆 | 1 |
| 太和殿 | 1 |
| 北京庙会 | 1 |
| 未来科学城 | 1 |
| 清华大学 | 1 |
| 神武门 | 1 |
| 冰糖葫芦 | 1 |
| 鸟巢 | 1 |

### 1.2 维度分布

| 维度码 | 样本数 |
|---|---|
| ANCIENT | 8 |
| RED | 5 |
| FOLK | 6 |
| TECH | 8 |
| MODERN | 4 |

## 2. 实验一：知识增强与多模态检索对比

评估口径：Known 27 条参与 Recall@1/Recall@5/MRR/Symbol Accuracy/Dimension Accuracy；Hallucination Rate 在全部 31 条上统计（输出具体符号但完全不含任何 KB 词表项 = 编造）。Hallucination Rate 基于 KB 词表子串判定，因此 Free 模式下模型输出整句描述时只要句中出现任一 KB 词条即不计为幻觉，该指标偏保守。

| Method | Recall@1 | Recall@5 | MRR | Symbol Accuracy | Dimension Accuracy | Hallucination Rate |
|---|---|---|---|---|---|---|
| Free | 0.0000 | 0.0000 | 0.0000 | 0.8519 | 0.8148 | 0.2258 |
| Text | 0.5185 | 0.7778 | 0.6481 | 0.7778 | 0.9259 | 0.0968 |
| Image | 0.1852 | 0.2963 | 0.2204 | 0.7407 | 0.8519 | 0.1290 |
| Multimodal | 0.5926 | 0.7778 | 0.6790 | 0.7037 | 0.9259 | 0.0645 |
| Multimodal Controlled | 0.5926 | 0.7778 | 0.6790 | 0.7037 | 0.9259 | 0.0000 |

**最佳检索方法**：
- Recall@1 最高：Multimodal（0.5926）；MRR 最高：Multimodal（0.6790）。
- Text vs Image：Text Recall@1=0.5185 vs Image Recall@1=0.1852；MRR 0.6481 vs 0.2204。纯 CLIP ViT-B/32 图像-图像检索在本数据集上几乎不具备判别力（Recall@5 仅 0.2963）。
- Multimodal vs Text：Multimodal Recall@1=0.5926 （Text 0.5185），MRR 0.6790 （Text 0.6481），Recall@5 0.7778 （Text 0.7778）。融合在检索排序上有稳定增益，但 Symbol Accuracy 未同步提升（Multimodal 0.7037 vs Text 0.7778）。
- Controlled 与 Hallucination：Multimodal Hallucination=0.0645 → Controlled=0.0000；Symbol Accuracy 保持 0.7037 不变（该批次中多模态输出本就落在闭集候选内，故幻觉下降未牺牲符号准确率）。
- Free 基线：Symbol Accuracy 0.8519，Recall@1 0.0000（无检索，不存在候选排序），Hallucination 0.2258。Free 的 Symbol Accuracy 来自输出整句描述与 GT 别名的子串匹配，不能等同于闭集检索能力。

## 3. 实验二：Unknown 拒识与 Identity Evidence Gate

Baseline = Existing Gate（三信号：检索分数、Top1-Top2 分差、KB 词表/场景负信号）；Proposed = Existing Gate 放行后再要求每个候选具备身份级证据（canonical/alias 完整实体命中或 KB 独特视觉属性命中），全部候选无身份证据则整条样本拒识。两种门控使用同一批视频、同一检索结果来源与同一 Pass-1 缓存；Free 模式不接入门控，两列共用同一结果。

| Method | Known Acc | Known Accept | Easy Unknown Reject | Hard Unknown Reject | False Reject | Hallucination |
|---|---|---|---|---|---|---|
| Existing Gate | 0.7556 | 0.8519 | 0.8000 | 0.1333 | 0.1481 | 0.1032 |
| + Identity Evidence Gate | 0.5556 | 0.6296 | 0.8000 | 0.4667 | 0.3704 | 0.0710 |

上表为 5 模式合并口径（含不接入门控的 Free，会稀释门控效果）。下表仅聚合 4 个接入门控的 KB 模式（Text/Image/Multimodal/Controlled）：

| Method (KB modes only) | Known Acc | Known Accept | Easy Unknown Reject | Hard Unknown Reject | False Reject | Hallucination |
|---|---|---|---|---|---|---|
| Existing Gate | 0.7315 | 0.8148 | 1.0000 | 0.1667 | 0.1852 | 0.0726 |
| + Identity Evidence Gate | 0.4815 | 0.5370 | 1.0000 | 0.5833 | 0.4630 | 0.0323 |

**关键发现（KB 模式聚合）**：
- Hard Unknown 拒识率 0.1667 → 0.5833，Known 接受率 0.8148 → 0.5370，Known 符号准确率 0.7315 → 0.4815。Identity Gate 确实提高了 Hard Unknown 拒识，但同时把大量 Known 样本误拒，二者是同一机制的两面，不能只报收益。
- Image 模式是主要拖累：Identity Gate 要求候选的规范名/别名出现在Pass-1 场景描述中，而纯图像检索的候选来自 CLIP 相似度、其名称几乎不会出现在场景描述里，因此该模式下 Identity Gate 退化为「全部拒识」（Known 全部 false rejection，准确率 0）。这说明身份证据门控只能与文本侧证据同源的检索模式配合，不能直接套在纯图像检索上。
- Text/Multimodal 模式下 Identity Gate 的收益有限：Hard Unknown 中神武门、人民大会堂两条视频的画面主体被 VLM 明确写成「故宫」「天安门广场」，这两个父实体/近邻实体在 KB 中存在，于是产生了合法的强身份证据并被放行——这正是「高相似但不是同一文化符号」的错误放行，文本身份证据无法区分。
- 两种门控的对比包含一次独立的 GLM-4V 采样（Prompt 不同导致重新调用），未做多次采样平均，因此单条样本的差异含采样噪声；结论只应看聚合趋势。


### 3.1 分模式结果

| Gate | Mode | Known Acc | Known Accept | Hard Unknown Reject | Easy Unknown Reject | False Reject | Hallucination |
|---|---|---|---|---|---|---|---|
| Existing Gate | Free | 0.8519 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.2258 |
| Existing Gate | Text | 0.7778 | 0.8148 | 0.0000 | 1.0000 | 0.1852 | 0.0968 |
| Existing Gate | Image | 0.7407 | 0.8519 | 0.0000 | 1.0000 | 0.1481 | 0.1290 |
| Existing Gate | Multimodal | 0.7037 | 0.8148 | 0.0000 | 1.0000 | 0.1852 | 0.0645 |
| Existing Gate | Multimodal Controlled | 0.7037 | 0.7778 | 0.6667 | 1.0000 | 0.2222 | 0.0000 |
| + Identity Evidence Gate | Free | 0.8519 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.2258 |
| + Identity Evidence Gate | Text | 0.5926 | 0.6296 | 0.3333 | 1.0000 | 0.3704 | 0.0645 |
| + Identity Evidence Gate | Image | 0.1852 | 0.2593 | 1.0000 | 1.0000 | 0.7407 | 0.0000 |
| + Identity Evidence Gate | Multimodal | 0.5556 | 0.6296 | 0.3333 | 1.0000 | 0.3704 | 0.0645 |
| + Identity Evidence Gate | Multimodal Controlled | 0.5926 | 0.6296 | 0.6667 | 1.0000 | 0.3704 | 0.0000 |

## 4. Hard Unknown 专项分析

Hard Unknown 共 3 条（人民大会堂、人民大会堂1、神武门）：真实符号不在 KB，但 KB 中存在同维度/父实体/视觉高度相似的候选。此类样本是「高相似但非同一文化符号」错误放行的主要来源。

| 视频 | 模式 | Top1 候选 | Top1 主分数 | Identity Evidence(+Gate) | Existing Gate | Identity Gate | 基线拒识 | Identity 拒识 | 错误类型 |
|---|---|---|---|---|---|---|---|---|---|
| 人民大会堂 | Text | 天安门广场 | 6.0000 | strong | confident | pass | 否 | 否 | hard_unknown_false_accept |
| 人民大会堂 | Image | 北大红楼 | 0.9080 | none | confident | reject | 否 | 是 | correctly_rejected |
| 人民大会堂 | Multimodal | 天安门广场 | 0.9255 | strong | confident | pass | 否 | 否 | hard_unknown_false_accept |
| 人民大会堂 | Multimodal Controlled | 天安门广场 | 0.9255 | strong | confident | pass | 是 | 是 | correctly_rejected |
| 人民大会堂1 | Text | 天安门广场 | 3.0000 | none | confident | reject | 否 | 是 | correctly_rejected |
| 人民大会堂1 | Image | 北大红楼 | 0.9077 | none | confident | reject | 否 | 是 | correctly_rejected |
| 人民大会堂1 | Multimodal | 天安门广场 | 0.9087 | none | confident | reject | 否 | 是 | correctly_rejected |
| 人民大会堂1 | Multimodal Controlled | 天安门广场 | 0.9087 | none | confident | reject | 是 | 是 | correctly_rejected |
| 神武门 | Text | 故宫 | 12.0000 | strong | confident | pass | 否 | 否 | hard_unknown_false_accept |
| 神武门 | Image | 都江堰 | 0.9368 | none | confident | reject | 否 | 是 | correctly_rejected |
| 神武门 | Multimodal | 故宫 | 0.9359 | strong | confident | pass | 否 | 否 | hard_unknown_false_accept |
| 神武门 | Multimodal Controlled | 故宫 | 0.9359 | strong | confident | pass | 否 | 否 | hard_unknown_false_accept |
- Existing Gate：Hard Unknown 拒识 2/15（0.1333）。
- + Identity Evidence Gate：Hard Unknown 拒识 7/15（0.4667）。


## 5. Error Analysis

| 错误类型 | 出现次数 |
|---|---|
| false_rejection | 70 |
| hard_unknown_false_accept | 21 |
| retrieval_error | 17 |
| final_selection_error | 6 |
| easy_unknown_false_accept | 2 |

错误类型定义：`retrieval_error`（GT 未进 Top-5）、`ranking_error`（GT 在 Top-5 但非 Top-1）、`final_selection_error`（GT 已在 Top-1 但模型选了别的符号）、`false_rejection`（Known 被拒识）、`hard_unknown_false_accept`/`easy_unknown_false_accept`（Unknown 被错误放行为具体符号）、`insufficient_identity_evidence`（Identity Gate 拒识但仍输出符号，理论不应出现，用于审计）。

- `missing_image_evidence`：18 条记录（3 条视频）的 GT 符号在 KB 中没有可用的真实参考图，其图像分缺失（不参与图像排序，记为 0），这些样本的图像检索在原理上不可能命中，已在明细中标记 `image_evidence_status=unavailable`，未使用文本编码伪造图像证据。


## 6. 最终结论

1. 本实验基于 31 条人工核验文化视频（Known 27 / Easy Unknown 1 / Hard Unknown 3），样本量小且类别不均衡，作为方法验证集而非大规模评测集，结论不宜外推为通用性能排名。
2. 检索层面，文本关键词检索是主要有效信号（Recall@1 0.5185）；CLIP ViT-B/32 纯图像检索在本域几乎不可用（Recall@1 0.1852），文本+图像融合带来小幅稳定增益（Recall@1 0.5926，MRR 0.6790）。Multimodal 优于 Text 主要体现在候选排序，而非最终符号准确率。
3. Controlled 输出约束把幻觉率由 0.0645 降到 0.0000，Known 符号准确率不变（0.7037），即本批次中闭集约束只削减了幻觉、未牺牲已知符号召回。
4. Identity Evidence Gate 把整体 Hard Unknown 拒识率由 0.1333 变为 0.4667，已知符号接受率由 0.8519 变为 0.6296，Known 符号准确率 0.7556 → 0.5556。该门控的收益与代价均明确存在，不应笼统声称单向提升。由于当前 KB 尚无 OCR / 参考图级身份证据，Image 模式会被全拒识，净效果在本数据上为负（Known 准确率下降），因此 Identity Evidence Gate 目前只能作为「可审计的候选级证据层」而非可直接上线的拒识策略。
5. 剩余错误集中在两类：一是 Known 样本在图像证据缺失或纯图像检索下被拒识（false_rejection），二是 Hard Unknown 在场景描述中确实出现了父实体/近邻实体名称时被身份证据误认为同一符号（hard_unknown_false_accept）。后者说明「文本身份证据」无法替代图像级/OCR级身份证据，是后续工作方向。
