# 第二步：证据加权与双路候选排序

2026-11-12实现。新策略名evidence_v1，通过显式参数启用；默认仍为legacy。尚未用独立验证集重新标定门控，未覆盖历史实验结果，也未调用GLM。

## 实现

新排序使用固定尺度的text_evidence_strength，不按单次查询最高分归一化。规范名/别名文本命中为0.8；清楚转录文字完整等于规范名/别名为1.0；普通关键词/特征按KB词项稀有度加权且总强度上限0.35；湖面、石狮等通用词只给0.02的弱相关性。相同词在多个字段/查询中重复出现不叠加。ASCII名称采用词边界，避免CBD匹配到其他英文串。

文本与图像各取max(10,top_k)个候选，按symbol_id合并去重，然后重排。清楚文字名称优先于描述中的名称，名称优先于只有弱特征的相关项；层内按fusion_alpha×文本证据强度+(1-fusion_alpha)×图像分排序。纯图像alpha=0不启用文本优先；纯文本alpha=1不从图像分支召回。地域/维度筛选同时约束两路候选。

名称优先只是候选排序规则，不等于身份成立；父子实体仍由身份核验模块判定。更长牌名包含父实体名时不算清楚文字精确命中父实体。当前文本名称通道仍可能因Pass-1误认地标而给错误候选高优先级，因此需要后续独立验证。

ranking_score、retrieval_evidence与text_evidence_strength单独落盘；原text_score/image_score/fusion_score/score沿用旧算法，供现有门控兼容和配对检查，不能把新排序强度当作已校准的概率。新候选分布仍会影响门控，所以trace明确标记experimental_unrecalibrated，不能视为旧门控阈值在新排序上已经有效。

## 配对开发回放

使用同一批历史Pass-1描述，对可访问视频本地重新计算完整CLIP图像分数；两种排序共享同一份图像分数，避免拿历史Top-5截断分数冒充全库候选。共30条可回放（27 Known、3 Unknown）；神武门原视频缺失，跳过并记录。没有GLM调用，没有运行最终标注或重新评估Unknown拒识。

| Known检索指标 | legacy | evidence_v1 |
|---|---:|---:|
| Recall@1 | 16/27 = 59.26% | 16/27 = 59.26% |
| Recall@5 | 21/27 = 77.78% | 22/27 = 81.48% |
| MRR@5 | 0.6790 | 0.7037 |

中关村展示中心由Top-5之外进入Top-5；人民英雄纪念碑两条样本Top-1改善；cbd2与故宫Top-1退步。净Top-1没有提升，故不直接替换默认策略，也不继续针对这些测试样本调权重。当前样本已参与开发诊断，以上数字不能作为独立测试收益。

额外复用第一步北大1的结构化证据与“北京大学”文字转录，旧/新排序Top-1均为北京大学。说明第一步收益得以保留，不能把同一个提升重复算作第二步收益。

## 使用

```bash
# 运行实验排序，配合第一步默认的结构化描述与按需文字识别
python scripts/run_annotation.py --video data/test/鸟巢.mp4 --retrieval-strategy evidence_v1

# 独立文化入口同样支持（只限multimodal检索）
python scripts/innovation2/run_cultural_rag.py --video data/test/鸟巢.mp4 --retriever multimodal --retrieval-strategy evidence_v1

# 复现离线配对比较：CPU CLIP，不调用GLM
python scripts/innovation2/replay_evidence_ranking.py --output-dir experiments/innovation2/outputs/evidence_ranking_v1/replay_new
```

多GPU入口透传retrieval-strategy；不指定参数时保留legacy。仅关键词模式不支持此多模态双路策略，会明确报错。

22项回归测试通过，覆盖通用词降权、清楚文字优先、双路召回、重复词不增分、父实体牌名边界、旧门控分数不变、纯图像权重和双路过滤，以及先前全部场景证据/标注测试。源码编译检查通过。

[回放汇总](../../experiments/innovation2/outputs/evidence_ranking_v1/replay/summary.json)、[变化样本](../../experiments/innovation2/outputs/evidence_ranking_v1/replay/changed_cases.json)、[北大1结构化证据复用](../../experiments/innovation2/outputs/evidence_ranking_v1/structured_beida1/summary.json)。后续应冻结此开发版，在独立验证样本上评估并重新标定门控，再决定是否设为默认。
