> 最新开发进展见 [2026-11-12 H3实验记录](hybrid_accuracy_v3_20261112.md)。下文保留2026-10-17的历史审计，不能作为当前进度。

# 创新点2当前状态与 Hard Unknown 审计

生成日期：2026-10-17。本文只读取已保存的代码、GT、阈值和实验产物；没有调用 GLM、CLIP 或检索器重跑实验。创新点3未被读取、修改或执行。

## 1. 可复现实验资产

| 资产 | 当前事实 |
|---|---|
| 知识库 | `data/knowledge_base/chinese_cultural_symbols_v1.json`，版本 1.2，共62条：原有47条北京样本 + 15条全国扩展条目。当前保留60张带 provenance 的图片候选（北京47张、全国扩展13张），包含官方页面和百度百科 image-only 来源，均标记为 `candidate_unreviewed`，默认不进入检索。 |
| 标注划分 | `experiments/innovation2/data/eval/cultural_ablation_gt_v2.jsonl`：30 个素材，测试集 20（17 hit、3 gap），验证集 11（8 hit、3 gap）。`kb_coverage=gap` 只表示当前 KB 不覆盖，不是模型预测。 |
| 最新完整测试产物 | `experiments/innovation2/runs/cultural_ablation/gate_on_final/results.json`，100 条记录，即 20 个测试视频 × 5 个模式；配置启用现有拒识门控和 v4 确定性符号约束。`summary.csv` 是同一产物的汇总。 |
| 验证集门控依据 | `experiments/innovation2/cache/rejection_val_signals.json` 与 `experiments/innovation2/data/eval/rejection_thresholds.json`：11 条验证信号用于阈值选择，未使用 test 调参。 |
| 图表/对比数据 | `experiments/innovation2/runs/cultural_ablation/comparison_off_vs_final.csv`、`comparison_off_vs_final_gap_samples.csv`，以及 `experiments/innovation2/reports/rejection_gate_ablation_report/`。现有图表未分离 Hard/Easy Unknown。 |

历史 `20261015_143003`、`gate_on_test`、`gate_on_test_v2` 与 `gate_on_test_v3` 仍保留，但不是本文采用的最新结果。下文所有“当前结果”均来自 `gate_on_final`。

## 2. 当前实现核查

### 知识库与检索

`src/knowledge/symbol_kb.py` 加载知识库；`src/knowledge/retriever.py` 以场景描述中的规范名、别名和特征词做确定性关键词检索；`src/knowledge/multimodal_retriever.py` 保留 `text_score`、`image_score` 和 `fusion_score`，融合分为文本归一化分与图像分的加权和。

`src/knowledge/clip_encoder.py` 为视频采样帧和 KB 参考项编码。v1.2 新增条目的 `reference_images` 使用结构化记录，检索器兼容旧字符串和新对象列表；已有图片条目可进行真实参考图像—视频帧比对，空图片条目仍退回 KB 文本描述 embedding。只有带 `source_page_url`、`image_url`、本地路径和 SHA-256 的图片记录才可作为 reference-image evidence。

### RAG、Prompt 与拒识

`src/pipeline/cultural_rag.py` 的链路是：Pass-1 GLM 场景描述 → KB 词表扫描 → 文本或多模态候选 → `PromptManager` 动态注入候选 → Pass-2 GLM 标注。`scripts/innovation2/run_cultural_rag.py` 是单视频入口，`scripts/innovation2/run_cultural_ablation.py` 是现有批量消融入口。

`src/pipeline/prompt_manager.py` 会向 Prompt 注入 Top-K、检索分数及当前门控结论。`src/knowledge/rejection_gate.py` 只使用四类信号：Top-1 分数、Top1–Top2 相对分差、KB 词表命中数、场景是否含“无明确文化符号”。当前验证集选择的 image/multimodal 阈值为 `score_thr=0.4`、`margin_thr=0`、`require_keywords=true`；分差实际上没有参与拒识。

`CulturalRAGPipeline.enforce_symbol_constraint()` 只保证输出属于 Top-K 的规范名/别名或 `unknown_symbol`，并使用包含关系匹配。它不验证“画面中的具体实体是否就是候选实体”。例如“神武门”可在“故宫博物院（神武门）”中与故宫别名匹配，却仍然不能说明 KB 有“神武门”这一独立符号。

### 现有评估与限制

`src/experiments/ablation_metrics.py` 已统计 symbol accuracy、维度准确率、hallucination、unknown/gap rejection、检索 Recall@K 与 MRR。它将全部 `gap` 合并，无法区分 Hard Unknown 和 Easy Unknown。现有 `hallucination_rate` 也没有把“对 KB 外目标强配为父实体/近邻实体”统一计为错误，因此不能代替 identity-level forced-match 指标。

## 3. 最新真实测试结果

测试集 20 条，已覆盖符号 17 条，KB 缺口 3 条。下表转录自最新 `gate_on_final/summary.csv`；Known Symbol Accuracy 是该文件的 `hit_symbol_accuracy`，Known Accept Rate 由原始记录重算。

| 模式 | Known Symbol Accuracy | Known Accept Rate | Gap Rejection Rate | 当前 Hallucination Rate |
|---|---:|---:|---:|---:|
| Free | 76.47% | 100.00% (17/17) | 0.00% (0/3) | 20.00% |
| Text + existing gate | 70.59% | 76.47% (13/17) | 33.33% (1/3) | 5.00% |
| Image + existing gate | 64.71% | 76.47% (13/17) | 33.33% (1/3) | 10.00% |
| Multimodal + existing gate | 64.71% | 70.59% (12/17) | 33.33% (1/3) | 0.00% |
| Multimodal controlled + existing gate | 64.71% | 64.71% (11/17) | 33.33% (1/3) | 0.00% |

“当前 Hallucination Rate”沿用历史指标，不能说明 Hard Unknown 已解决：在 `multimodal_controlled` 下，3 个 gap 中仍有 2 个被放行并输出具体 KB 近邻，identity-level forced-match rate 是 **66.67% (2/3)**。这正是该指标漏记的问题。

## 4. Hard Unknown 分析集

已生成 [`cultural_unknown_analysis.csv`](../../experiments/innovation2/results/cultural_rag/unknown_analysis/cultural_unknown_analysis.csv)。它包含：

- 100 行已保存的最终测试记录（20 视频 × 5 模式）；
- 11 行验证集已保存信号；验证集没有对应的最终预测或候选名称，因此这些字段明确保留为空，未补造预测；
- 用户要求的原始字段，以及 `split`、`mode`、`relative_margin`、`category_evidence`、`identity_evidence` 和 `source`。

Unknown 类型由 GT 备注和 KB 覆盖关系人工审计确定，不由模型预测确定：

| 类型 | 已审计样本 | 划分理由 |
|---|---|---|
| Known | 所有 `kb_coverage=hit` 样本 | GT 给出了目标 KB symbol_id。 |
| Hard Unknown | 神武门、中关村国际创新中心、人民大会堂1（测试）；人民大会堂、中关村展示中心（验证） | KB 中存在父实体、同地域/功能实体或同维度近邻。 |
| Easy Unknown | 糖葫芦（验证） | KB 只有宽泛的民俗饮食近邻，名称和外观均没有具体近邻。 |

当前测试集没有 Easy Unknown；因此不能用测试集声称 Easy Unknown 结果。它只含 3 个 Hard Unknown，Hard Unknown Rejection Rate 与当前 Gap Rejection Rate 同为 **1/3 = 33.33%**。

## 5. 为什么现有拒识会失败

### Q1：Known 与 Hard Unknown 的 fusion score 是否重叠？

是。以主链 `multimodal_controlled` 为例，Known Top-1 fusion 平均值为 0.6918（范围 0.3158–0.8173）；Hard Unknown 平均值为 0.6465（范围 0.3187–0.8124）。被错误放行的神武门和中关村国际创新中心分别为 **0.8124**、**0.8085**，处在已知样本的高分区间。单一高分没有判别力。

### Q2：为何神武门和中关村国际创新中心会得到约 0.8？

神武门的场景描述含“故宫博物院”，它是 KB “故宫”的别名；中关村国际创新中心的描述含“中关村”，它是 KB “中关村”的规范名。关键词端把这些父实体/近邻名称归一化到 1.0，CLIP 分又约为 0.63，50:50 融合后分别得到 0.8124 和 0.8085。系统确认的是“与故宫/中关村有关”，却把它当成“就是 KB 中那个具体 symbol”。

### Q3：retrieval score 能否区分语义相关和具体身份一致？

不能。当前分数衡量的是文本、描述特征和图像文本空间的相似性。它没有一个字段要求 target 的 canonical name、alias、OCR 文字、独特外观或 reference image 与候选实体一致。尤其是当前 reference images 全缺失，图像端也没有具体参考地标证据。

### Q4：Top1–Top2 margin 有判别力吗？

现有数据不支持将其作为 Hard Unknown 解决方案。image 模式下 Known 相对分差平均 0.0055、Hard Unknown 平均 0.0012，均极小且重叠；multimodal 下两个错误放行的 Hard Unknown 分差反而为 0.6089、0.6109，分别不低于多数 Known。验证集网格搜索最终将 `margin_thr` 选为 0，等价于未使用该信号。

## 6. Category Evidence 与 Identity Evidence

当前 Prompt、候选和门控把下列两类证据混合为“confidence”：

| 证据层级 | 可支持的结论 | 例子 |
|---|---|---|
| `category_evidence` | 文化维度、建筑/园区/民俗小吃等类别相关 | 红墙黄瓦支持古建筑；“中关村”支持科技园区语义；国徽支持红色文化。 |
| `identity_evidence` | 某个具体 KB symbol 的身份成立 | 可读文字与候选 canonical name 或 alias 精确匹配；OCR 名称；候选独有视觉属性；同一实体的可靠参考图像；不可替代的场景上下文。 |

“故宫相关”不是“神武门条目存在”；“中关村相关”不是“中关村国际创新中心已被 KB 覆盖”。两者只能记为 category/parent evidence，不能作为具体 symbol 的接收依据。

## 7. 轻量 Identity Evidence Gate 设计（未实现）

保持当前 RAG、候选检索和 GLM 两阶段结构，只在现有 RejectionGate 后增加一个可审计的身份判断：

1. **Retrieval confidence**：保留现有 top-1、margin、关键词和场景负信号，作为“是否值得继续核验候选”。
2. **Identity evidence extraction**：对每个 Top-K 候选记录结构化证据，而非写入一个混合 confidence：
   - `canonical_name_exact_hit`、`alias_exact_hit`：候选名/别名与场景文本或 OCR 的精确实体命中；禁止用父实体或子串替代。
   - `ocr_name_evidence`：显式 OCR/可读名称与候选的 exact match；缺失时为 `null`，不假定存在。
   - `unique_visual_evidence`：与候选 KB 中唯一视觉属性的可核验对应；一般“古建筑”“玻璃楼”仅为类别证据。
   - `reference_image_evidence`：未来有经核验的 reference images 后才可使用；当前必须为 `null`。
   - `context_evidence`：地址、相邻地标、活动/场景等辅助证据，单独不能接收具体符号。
3. **决策**：仅当 retrieval confidence 通过且有至少一项强身份证据，或两项独立中等身份证据时，输出具体 candidate；否则输出 `unknown_symbol`。类别、父子包含、维度和单纯高 fusion 分只能保留为解释，不可接收具体 symbol。
4. **校准和评估**：只在当前 validation split 选择证据组合和阈值；固定后在 test 上一次性报告 Known Symbol Accuracy、Known Accept Rate、Unknown Rejection Rate、Hard Unknown Rejection Rate、identity-level Hallucination/Forced-Match Rate。不得根据神武门、中关村国际创新中心或测试分数调参。

该门控会正确把“故宫→神武门”和“中关村→中关村国际创新中心”视为身份不足，同时需要通过验证集监控对京剧、未来科学城等 Known 样本的误拒，避免把所有样本都拒绝。

## 8. 本阶段结论与下一步边界

本阶段已经完成当前代码、数据划分、最新结果、Hard Unknown 样本和失败原因的审计；没有修改检索、Prompt、门控、知识库，也没有重跑任何模型。后续若恢复实现，应先将 Identity Evidence Gate 写成独立、可落盘的证据层，然后仅用 validation 校准，再运行 Existing Gate 与 Identity Evidence Gate 的同一测试集对比。
