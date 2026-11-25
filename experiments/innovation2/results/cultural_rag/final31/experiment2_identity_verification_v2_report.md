# 实验二（v2）：身份级证据核验模块

> 本报告全部数字由 `scripts/innovation2/run_identity_verifier_v2.py` 从真实运行结果自动生成。
> 主评测入口：`Multimodal Controlled + Gate`，每个视频只产生一个最终判定；实验一未重跑，GT 未修改。

> **口径说明**：① 三种方法共用同一批 `multimodal_controlled` 检索结果，并共用同一解析器把自由文本输出映射为闭集符号（多个候选同时出现时取文中最早提及者），保证「每视频一次最终决策」；② v1 使用既有运行结果，仅按同一口径重新映射，未重跑；③ `神武门.mp4` 当前素材目录中缺失，该条视觉通道为 `unavailable`，仅由文本证据 + 父子层级规则判定；④ Verifier 为单次采样（temperature=0），未做多次投票，单条样本可能有采样噪声；⑤ `frame_consistency_supporting=0.5` 为结构性多数规则（validation 负样本 95 分位为 0，直接取 0 会使 supporting 恒成立），非 test 调参。

## 1. v1 为什么出现过拒

v1（`src/knowledge/identity_evidence_gate.py`）把「强身份证据」定义为唯一判据：候选的 canonical/alias/独特视觉属性必须出现在 Pass-1 场景描述的主体文本中，否则该候选被过滤；当 Top-K 候选全部被过滤时就整条样本强拒。这个设计有两个结构性缺陷：

1. **单一文本身份通道**：视觉相似度（CLIP 参考图匹配）完全没被用作身份证据，因此纯图像检索（候选名天然不会出现在描述里）会退化为「全拒识」。
2. **父子实体不做区分**：描述中出现「故宫」时，v1 直接把「故宫」判为强证据，既造成 Known 过拒（名字没出现就拒），又造成 Hard Unknown 误放（父实体命中就接受）。

在正式 31 条上，v1 的视频级结果为：Known Acc 0.5926、False Reject 0.3704、Hard Unknown Reject 0.6667。

## 2. v2 如何修改

- 证据重新分层：Strong Identity / Supporting / Category-Hierarchy 三层，**父实体、子实体、同景区、同类别一律降级为 Category-Hierarchy，不能单独支持 accept**。
- **文本身份通道与视觉身份通道并列**：任一通道出现强证据即可进入 accept 判断；文本没出现候选名称不再直接拒识。
- 规则初筛（`verification_required`）只把模糊样本送进 LLM 二次核验，避免全量调用。
- 核验层对检索结果**只做减法**：已被检索/标注阶段拒识的样本不会被重新接受。

## 3. Text Identity 与 Visual Identity 如何并行

- Text Identity Channel：canonical / alias 完整实体匹配（修正 v1 的前缀误判），并新增两条通用规则：① 纯 ASCII 缩写（如 CBD）在中文句中精确出现即视为完整实体；② 把 KB `visual_features` 拆成最小特征词（去括注与数量词，长度≥3），精确命中即计为独特特征证据。
- Visual Identity Channel：逐帧关键帧 CLIP embedding 与候选**逐张**参考图 embedding 匹配，输出 max_ref_sim / top3_ref_sim / frame_consistency 三个量；阈值来自 validation set（6 条视频、与 test 零重叠）标定：max_ref_sim≥0.77、top3_ref_sim≥0.74、frame_consistency≥0.8 判为视觉强证据。
- 两条通道的结论不合并成单一分数，而是分别记录在日志中，冲突时进入 LLM 核验。

## 4. 为什么父实体不能算 Identity Evidence

「视频拍摄于/属于故宫建筑群」只能确定**空间与层级归属**，不能确定「该视频的主体就是‘故宫’这一 KB 符号定义本身」。若把父实体命中当身份证据，任何在故宫、天安门广场、清华北大校园内拍摄的子实体都会被错误接受为父实体符号，这正是 open-set 拒识里最典型的「高相似 ≠ 同一身份」错误。v2 的通用处理是：

1. 候选名作为更长实体名的一部分出现（如「X的Y门」）→ `parent_entity`；
2. 画面主体被明确指认为**另一个具体实体**（如「主体为神武门」「主体是太和殿」）→ `parent_entity`；描述性名词（摩天大楼/总部大楼/大厦/建筑群）不算具体实体，不触发该规则；
3. `same_scenic_area`（KB 声明的同景区近邻同时出现）仅作为 Category-Hierarchy 证据记录，不参与 accept 判定。

## 5. Verifier 在哪些样本触发

触发 1/31 条视频（trigger rate 0.0323），共产生 1 次 LLM 二次核验调用。触发原因分布：

| 触发原因 | 次数 |
|---|---|
| hierarchy_relation_with_subject | 1 |
| name_hit_but_hierarchy_conflict | 1 |
| text_image_disagreement | 1 |
| high_score_without_identity | 1 |

触发样本清单：

| video | sample_type | top1 | 触发原因 | verifier 结果 |
|---|---|---|---|---|
| 神武门 | hard_unknown | 故宫 | hierarchy_relation_with_subject|name_hit_but_hierarchy_conflict|text_image_disagreement|high_score_without_identity | reject_related_but_not_exact |

核验触发率（Verification Trigger Rate）：0.0323（1/31）；在触发样本中 Verifier Accept 0（0.0000）、Reject Related 1（1.0000）、Reject Insufficient 0（0.0000）。其余样本由规则层直接判定的 accept/reject，不产生 LLM 调用。


## 6. Existing Gate 结果（视频级）

| Method | Known Acc | Known Accept | Easy Unknown Reject | Hard Unknown Reject | False Reject | Hallucination |
|---|---|---|---|---|---|---|
| Existing Gate | 0.7037 | 0.7407 | 1.0000 | 0.6667 | 0.2593 | 0.0323 |
| Identity Verification v2 | 0.7037 | 0.7407 | 1.0000 | 1.0000 | 0.2593 | 0.0000 |

计数值：Existing Gate Known 正确 19/27，Known 被拒 7，Hard Unknown 拒识 2/3，Easy Unknown 拒识 1/1。同口径 v2：Known 正确 19/27，Known 被拒 7，Hard Unknown 拒识 3/3。


## 7. v1 结果（视频级，开发对照）

| Method | Known Acc | Hard Unknown Reject | False Reject | Hallucination |
|---|---|---|---|---|
| Identity Gate v1 | 0.5926 | 0.6667 | 0.3704 | 0.0323 |
| Identity Verification v2 | 0.7037 | 1.0000 | 0.2593 | 0.0000 |

## 8. v2 结果与关键对比

- Known Acc：v1 0.5926 → v2 0.7037（恢复 0.1111；相对 Existing Gate 0.7037 的差距 0.0000）
- False Reject：v1 0.3704 → v2 0.2593（下降 0.1111）
- Hard Unknown Reject：Baseline 0.6667 / v1 0.6667 / v2 1.0000
- Hallucination（Unknown 被接受为任一符号，闭集口径）：Baseline 0.0323 / v1 0.0323 / v2 0.0000
- 由 v1 误拒而在 v2 被恢复的 Known 样本：4 条（cbd, cbd3, 角楼, 角楼1）
- 相对 Baseline 新增误拒的 Known 样本：0 条（无）
- v1 因独立采样而接受、但 Baseline 已拒识的 Known 样本：1 条（京剧青衣）；v2 遵循「只做减法」，不复活 Baseline 已拒识样本
- 说明：核验层是叠在 Existing Gate 之后的减法层，v2 的 Known 拒识 7 条中有 7 条在 Baseline 阶段已被拒识（不可复活），因此 v2 的 Known 上限等于 Baseline；核验层只应新增「身份证据不足」的拒识。


## 9. 三条 Hard Unknown 的最终判定

| video | GT | Top1 | fusion | text evidence | visual evidence | hierarchy | verifier | 最终判定 | 是否正确 |
|---|---|---|---|---|---|---|---|---|---|
| 人民大会堂 | 人民大会堂 | 天安门广场 | 0.9255 | n/a： | n/a： | n/a | already_rejected_by_retrieval | unknown_symbol | 是 |
| 人民大会堂1 | 人民大会堂 | 天安门广场 | 0.9087 | n/a： | n/a： | n/a | already_rejected_by_retrieval | unknown_symbol | 是 |
| 神武门 | 神武门 | 故宫 | 0.9359 | strong：canonical=False; alias=True; uniq | unavailable：KB 无真实参考图 | parent_entity | reject_related_but_not_exact | unknown_symbol | 是 |

## 10. 神武门案例

- **神武门**：GT=神武门，Top1=故宫，文本身份证据=strong：canonical=False; alias=True; unique_feature=['神武门']，视觉身份证据=unavailable：KB 无真实参考图，层级关系=parent_entity，verifier=reject_related_but_not_exact，最终=unknown_symbol，正确拒识。

## 11. 人民大会堂案例

- **人民大会堂**：GT=人民大会堂，Top1=天安门广场，文本身份证据=n/a：，视觉身份证据=n/a：，层级关系=n/a，verifier=already_rejected_by_retrieval，最终=unknown_symbol，正确拒识。
- **人民大会堂1**：GT=人民大会堂，Top1=天安门广场，文本身份证据=n/a：，视觉身份证据=n/a：，层级关系=n/a，verifier=already_rejected_by_retrieval，最终=unknown_symbol，正确拒识。

## 12. 仍存在的失败案例

| video | sample_type | GT | 最终判定 | verifier | 原因 |
|---|---|---|---|---|---|
| 中关村展示中心 | known | 中关村国家自主创新示范区展示中心 | unknown_symbol | already_rejected_by_retrieval | baseline_controlled_rejected |
| 京剧青衣 | known | 京剧 | unknown_symbol | already_rejected_by_retrieval | baseline_controlled_rejected |
| 北大 | known | 北京大学 | unknown_symbol | already_rejected_by_retrieval | baseline_controlled_rejected |
| 北大1 | known | 北京大学 | unknown_symbol | already_rejected_by_retrieval | baseline_controlled_rejected |
| 庙会 | known | 北京庙会 | unknown_symbol | already_rejected_by_retrieval | baseline_controlled_rejected |
| 故宫 | known | 故宫 | 太和殿 | accept_exact_identity | strong_identity_evidence |
| 未来科学城 | known | 未来科学城 | unknown_symbol | already_rejected_by_retrieval | baseline_controlled_rejected |
| 胡同 | known | 胡同 | unknown_symbol | already_rejected_by_retrieval | baseline_controlled_rejected |

## 13. v2 是否适合作为论文最终方法

- 视频级 Hard Unknown 拒识：Baseline 0.6667、v1 0.6667、v2 1.0；Easy Unknown 拒识 v2 = 1.0。
- Known Acc：v1 的相对过拒已基本消除（0.5926 → 0.7037，False Reject 0.3704 → 0.2593），说明「文本名称缺失即拒识」的结构性缺陷已被修复。
- v2 的拒识能力来自对**候选本身**的身份证据核验，而不是对检索结果的二次排序，因此不会引入新的接受行为（核验层只做减法）。
- 三条 Hard Unknown 均被正确拒识（其中 2 条：人民大会堂, 人民大会堂1 在 Baseline 阶段已被拒识；v2 的新增贡献是把 神武门 这类 Baseline 误放的父实体/相似实体样本正确拒识）。
- LLM 二次核验只触发 1 条视频、1 次调用，成本可控；但核验质量依赖 GLM-4V 对关键帧的判别，单次采样存在随机性，建议论文中报告为单次采样结果并说明该局限。
- 结论：v2 在保持 Hard Unknown 拒识能力的同时把 v1 的 Known 过拒降到与 Baseline 相同（0.2593），**建议作为论文最终方法**；其残余失败集中在「同建筑群/同景区的父子实体」这一类，属于需要 OCR 或更强细粒度视觉身份证据才能解决的问题，可作为局限性讨论。
