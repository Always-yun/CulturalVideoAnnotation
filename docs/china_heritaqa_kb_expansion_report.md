# ChinaHeritaQA 驱动的中华文化符号知识库扩充报告（v2 候选）

- 日期：2026-10-27
- 范围：仅做实体提取 → 去重 → 五维映射 → 官方来源核验 → 候选生成 → 参考图收集
- 未执行：Text/Image/Multimodal 消融实验、Identity Gate、GLM 调用、创新点3
- v1 知识库与既有实验结果**未修改、未覆盖**；本轮产物全部为 `v2_candidates`，`review_status=pending`

## 1. 数据源实际规模

| 指标 | 数值 |
|---|---|
| ChinaHeritaQA 站点实体 | 51（文化 35 / 自然 12 / 双遗产 4） |
| 图像数量（元数据口径） | 2279 |
| 问答数量 | 14133（q1–q7） |
| 仓库内实际图像文件 | 23（仅样例，2279 张原图未随仓库发布） |
| 可参与文化符号提取的实体 | **39**（35 文化 + 4 双遗产） |
| 自然遗产（不纳入） | 12 |

## 2. 实体提取与去重

| 结果 | 数量 |
|---|---|
| 可视文化符号候选（提取后） | **39**（35 文化 + 4 双遗产） |
| 与 v1 重复（existing） | **10** |
| 新候选（new_candidate） | **29** |
| 视觉可识别性 low | 3（保留在候选表但标记 low，不建议本轮入库） |
| 自然遗产排除 | 12 |

去重方法：规范名精确匹配 → 别名（v1 `aliases` 按 `|`/`;` 拆分）→ 英文名 → 地域辅助判断，人工复核。
重复命中明细：

| ChinaHeritaQA 实体 | 命中 v1 symbol_id | v1 规范名 |
|---|---|---|
| 良渚古城遗址 | CN_ANCIENT_004 | 良渚古城遗址 |
| 北京中轴线 | BJ_GUDU_006 | 北京中轴线 |
| 布达拉宫 | CN_ANCIENT_003 | 布达拉宫 |
| 故宫 | BJ_GUDU_001 | 故宫 |
| 秦始皇陵及兵马俑坑 | CN_ANCIENT_001 | 秦始皇陵及兵马俑坑 |
| 莫高窟 | CN_ANCIENT_002 | 莫高窟 |
| 泉州：宋元中国的世界海洋商贸中心 | CN_MODERN_002 | 泉州：宋元中国的世界海洋商贸中心 |
| 天坛 | BJ_GUDU_003 | 天坛 |
| 杭州西湖文化景观 | CN_MODERN_001 | 杭州西湖文化景观 |
| 云岗石窟 | CN_ANCIENT_005 | 云岗石窟 |

> 说明：故宫（含沈阳故宫）、布达拉宫（含大昭寺/罗布林卡）在数据集中为复合实体，v1 只覆盖主项，
> 按“不新建重复 symbol”的要求本轮标记 existing，子项缺口写入 notes，留待后续单独评估。

## 3. 五维分布（按主维度计，new_candidate）

| 维度 | 名称 | 数量 |
|---|---|---|
| ANCIENT | 古城与历史文化 | 22 |
| RED | 红色文化 | 0 |
| FOLK | 民族与民俗文化 | 5 |
| TECH | 科技与创新文化 | 0 |
| MODERN | 现代城市与国际文化 | 2 |
| **合计** | — | **29** |

- RED = 0：ChinaHeritaQA 不含革命旧址/红色地标，未做任何“近现代建筑→RED”的硬映射；
- TECH = 0：无科技工程/科技场馆类实体，未把古水利工程（都江堰）误归 TECH；
- MODERN = 2（鼓浪屿、开平碉楼；澳门、丽江、哈尼梯田等按 ANCIENT/FOLK 主维度，MODERN 仅作并列维度）。

多维度候选（主维度;并列维度）：红河哈尼梯田文化景观(FOLK;ANCIENT)、普洱景迈山古茶林文化景观(FOLK;ANCIENT)、福建土楼(FOLK;ANCIENT)、澳门历史城区(ANCIENT;MODERN)、开平碉楼与村落(MODERN;ANCIENT)、鼓浪屿：历史国际社区(MODERN;ANCIENT)、丽江古城(FOLK;ANCIENT)、左江花山岩画文化景观(FOLK;ANCIENT)

## 4. 地域、可识别性与来源覆盖

- 主要省市：云南省 3、福建省 3、跨省 3、山西省 2、河南省 2、四川省 2、北京市 2、山东省 2、湖北省 1、吉林省 1、江苏省 1、重庆市 1、澳门特别行政区 1、广东省 1、河北省 1、内蒙古自治区 1、广西壮族自治区 1、安徽省 1
- visual_recognizability：high 21 / medium 5 / low 3
- 有 A 级官方来源（国家文物局）的候选：**28/29 = 96.6%**
- 官方页面 HTTP 核验通过：**28/29**（页面可访问且标题与实体一致）
- 有至少 1 张 A 级参考图的候选：**28/29 = 96.6%**
- 有效参考图片总数：**78** 张（每候选 2–3 张）
- 无官方来源/无图候选：普洱景迈山古茶林文化景观

## 5. 参考图片收集与质量检查

来源策略：仅使用 **A 级官方来源**——国家文物局“世界文化遗产名录”对应遗产页（`www.ncha.gov.cn/art/.../art_2791_*.html`），
不使用 AI 生成图、百度缩略图、小红书/微博普通用户、旅游博客、商业图库。

每张图记录 provenance：`symbol_id / local_path / image_url / source_page_url / source_organization / authority_level / caption / retrieval_date / license / image_status`，落盘于
`data/knowledge_base/reference_images_manifest_v2.json`；候选表 `reference_images` 字段回填本地相对路径。

自动质量检查（`data/china_heritaqa/reference_image_qc.json`）：

| 检查项 | 规则/结果 |
|---|---|
| 可正常打开、真实图像 | PIL `verify()` + 重新解码，非 HTML 错误页 |
| 分辨率 | 宽 ≥400、高 ≥260（实测全部 600px 宽级别） |
| 宽高比 | 0.4–3.0 |
| 空白/纯色图 | 灰度标准差 ≥8 |
| 重复图 | SHA256 全局去重 |
| logo/二维码/网页截图 | 页面正文 `picture` 目录 + 尺寸/比例过滤，人工抽查未见 |
| 相关性 | CLIP ViT-B/32 图文相似度打分（均值 0.243），<0.20 标记 `relevance_low` 供人工复核 |

QC 计数：保留 78 张入 manifest；排除 6 张（分辨率不足等）；42 张通过 QC 但未进入每符号 Top-3。
> 说明：下载目录 `reference_images_v2/` 为下载池，包含首轮按页面顺序选取后被替换的重复图；
> **统计与入库一律以 manifest 为准（78 张）**。

逐候选图片覆盖：

| symbol_id | 规范名 | 图片数 | 分辨率 |
|---|---|---|---|
| CN2_ANCIENT_001 | 武当山古建筑群 | 3 | 605x311、602x401、602x427 |
| CN2_ANCIENT_002 | 平遥古城 | 3 | 600x400、600x400、600x400 |
| CN2_ANCIENT_003 | 高句丽王城、王陵及贵族墓葬 | 3 | 600x405、600x288、600x450 |
| CN2_ANCIENT_004 | 苏州古典园林 | 2 | 600x333、600x900 |
| CN2_FOLK_001 | 红河哈尼梯田文化景观 | 2 | 600x403、600x429 |
| CN2_FOLK_002 | 普洱景迈山古茶林文化景观 | 0 | — |
| CN2_ANCIENT_005 | 大足石刻 | 3 | 600x900、600x400、600x400 |
| CN2_FOLK_003 | 福建土楼 | 3 | 600x402、600x402、600x400 |
| CN2_ANCIENT_006 | 澳门历史城区 | 3 | 600x400、600x414、600x370 |
| CN2_ANCIENT_007 | 登封“天地之中”历史古迹 | 3 | 600x483、600x399、600x400 |
| CN2_ANCIENT_008 | 明清皇家陵寝 | 3 | 600x360、600x400、600x400 |
| CN2_MODERN_001 | 开平碉楼与村落 | 3 | 600x364、600x399、600x900 |
| CN2_MODERN_002 | 鼓浪屿：历史国际社区 | 3 | 600x424、600x392、600x561 |
| CN2_ANCIENT_009 | 龙门石窟 | 2 | 600x900、600x394 |
| CN2_ANCIENT_010 | 青城山—都江堰 | 3 | 600x900、600x902、600x399 |
| CN2_ANCIENT_011 | 五台山 | 3 | 600x400、600x399、600x399 |
| CN2_ANCIENT_012 | 承德避暑山庄及其周围寺庙 | 3 | 600x400、600x400、600x400 |
| CN2_FOLK_004 | 丽江古城 | 3 | 600x720、600x398、600x839 |
| CN2_ANCIENT_013 | 周口店北京人遗址 | 3 | 600x400、600x400、600x399 |
| CN2_ANCIENT_014 | 元上都遗址 | 3 | 600x381、600x450、600x600 |
| CN2_ANCIENT_015 | 颐和园 | 3 | 600x450、600x400、600x400 |
| CN2_ANCIENT_016 | 曲阜孔庙、孔林和孔府 | 3 | 600x399、600x399、600x399 |
| CN2_ANCIENT_017 | 长城 | 3 | 600x400、600x900、600x400 |
| CN2_ANCIENT_018 | 土司遗址 | 3 | 600x399、600x400、600x906 |
| CN2_FOLK_005 | 左江花山岩画文化景观 | 3 | 600x400、600x386、600x600 |
| CN2_ANCIENT_019 | 峨眉山—乐山大佛 | 2 | 600x392、600x892 |
| CN2_ANCIENT_020 | 黄山 | 2 | 600x631、600x600 |
| CN2_ANCIENT_021 | 泰山 | 3 | 600x386、600x900、600x400 |
| CN2_ANCIENT_022 | 武夷山 | 2 | 600x294、600x474 |

## 6. 名称歧义与不建议入库的实体

名称歧义/粒度问题：

- 鼓浪屿：历史国际社区：“鼓浪屿公共租界”为数据集译名，通用名为“鼓浪屿：历史国际社区”
- 青城山—都江堰：官方名称为复合遗产（青城山+都江堰），单一 symbol 同时承载道教名山与水利工程，视觉特征需并列
- 曲阜孔庙、孔林和孔府：复合遗产（孔庙+孔林+孔府），三者空间相邻，按一体的“三孔”处理
- 长城：线性跨省遗产，不同段落（八达岭/慕田峪/嘉峪关）视觉差异明显，单一 symbol 易混淆具体段
- 峨眉山—乐山大佛：复合遗产（峨眉山+乐山大佛），两者视觉差异大，后续可拆分

不建议进入正式 KB：

| 实体 | 原因 |
|---|---|
| 巴丹吉林沙漠——沙山湖泊群 | 自然遗产，不属中华文化符号五维体系 |
| 中国丹霞 | 自然遗产，不属中华文化符号五维体系 |
| 梵净山 | 自然遗产，不属中华文化符号五维体系 |
| 黄龙风景名胜区 | 自然遗产，不属中华文化符号五维体系 |
| 湖北神农架 | 自然遗产，不属中华文化符号五维体系 |
| 中国黄（渤）海候鸟栖息地（第二期） | 自然遗产，不属中华文化符号五维体系 |
| 三清山国家公园 | 自然遗产，不属中华文化符号五维体系 |
| 可可西里 | 自然遗产，不属中华文化符号五维体系 |
| 四川大熊猫栖息地 | 自然遗产，不属中华文化符号五维体系 |
| 中国南方喀斯特 | 自然遗产，不属中华文化符号五维体系 |
| 武陵源风景名胜区 | 自然遗产，不属中华文化符号五维体系 |
| 天山山脉 | 自然遗产，不属中华文化符号五维体系 |
| 周口店北京人遗址 | visual_recognizability=low：古人类遗址地表遗存弱，视频/图像难以稳定识别 |
| 元上都遗址 | visual_recognizability=low：元代都城遗址地表遗存弱，视频/图像难以稳定识别 |
| 土司遗址 | visual_recognizability=low：土司制度遗址地表遗存弱，视频/图像难以稳定识别 |

## 7. 推荐优先纳入正式 KB 的候选（按优先级）

优先级规则：P1 = high 且视觉符号性强；P2 = medium 或复合遗产需拆分；P3 = low，暂缓。

| # | 优先级 | 规范名 | symbol_id | 主维度 | 省份 | 可识别性 | 参考图 | q1样本数 |
|---|---|---|---|---|---|---|---|---|
| 1 | P1 | 大足石刻 | CN2_ANCIENT_005 | 古城与历史文化 | 重庆市 | high | 3 | 313 |
| 2 | P1 | 武当山古建筑群 | CN2_ANCIENT_001 | 古城与历史文化 | 湖北省 | high | 3 | 183 |
| 3 | P1 | 龙门石窟 | CN2_ANCIENT_009 | 古城与历史文化 | 河南省 | high | 2 | 132 |
| 4 | P1 | 福建土楼 | CN2_FOLK_003 | 民族与民俗文化 | 福建省 | high | 3 | 110 |
| 5 | P1 | 平遥古城 | CN2_ANCIENT_002 | 古城与历史文化 | 山西省 | high | 3 | 104 |
| 6 | P1 | 开平碉楼与村落 | CN2_MODERN_001 | 现代城市与国际文化 | 广东省 | high | 3 | 72 |
| 7 | P1 | 颐和园 | CN2_ANCIENT_015 | 古城与历史文化 | 北京市 | high | 3 | 52 |
| 8 | P1 | 澳门历史城区 | CN2_ANCIENT_006 | 古城与历史文化 | 澳门特别行政区 | high | 3 | 51 |
| 9 | P1 | 苏州古典园林 | CN2_ANCIENT_004 | 古城与历史文化 | 江苏省 | high | 2 | 50 |
| 10 | P1 | 峨眉山—乐山大佛 | CN2_ANCIENT_019 | 古城与历史文化 | 四川省 | high | 2 | 42 |
| 11 | P1 | 红河哈尼梯田文化景观 | CN2_FOLK_001 | 民族与民俗文化 | 云南省 | high | 2 | 38 |
| 12 | P1 | 黄山 | CN2_ANCIENT_020 | 古城与历史文化 | 安徽省 | high | 2 | 33 |
| 13 | P1 | 长城 | CN2_ANCIENT_017 | 古城与历史文化 | 跨省 | high | 3 | 24 |
| 14 | P1 | 五台山 | CN2_ANCIENT_011 | 古城与历史文化 | 山西省 | high | 3 | 20 |
| 15 | P1 | 青城山—都江堰 | CN2_ANCIENT_010 | 古城与历史文化 | 四川省 | high | 3 | 17 |
| 16 | P1 | 丽江古城 | CN2_FOLK_004 | 民族与民俗文化 | 云南省 | high | 3 | 12 |
| 17 | P1 | 鼓浪屿：历史国际社区 | CN2_MODERN_002 | 现代城市与国际文化 | 福建省 | high | 3 | 10 |
| 18 | P1 | 泰山 | CN2_ANCIENT_021 | 古城与历史文化 | 山东省 | high | 3 | 4 |
| 19 | P1 | 曲阜孔庙、孔林和孔府 | CN2_ANCIENT_016 | 古城与历史文化 | 山东省 | high | 3 | 3 |
| 20 | P1 | 承德避暑山庄及其周围寺庙 | CN2_ANCIENT_012 | 古城与历史文化 | 河北省 | high | 3 | 2 |
| 21 | P1 | 武夷山 | CN2_ANCIENT_022 | 古城与历史文化 | 福建省 | high | 2 | 1 |
| 22 | P2 | 明清皇家陵寝 | CN2_ANCIENT_008 | 古城与历史文化 | 跨省 | medium | 3 | 91 |
| 23 | P2 | 高句丽王城、王陵及贵族墓葬 | CN2_ANCIENT_003 | 古城与历史文化 | 吉林省 | medium | 3 | 22 |
| 24 | P2 | 普洱景迈山古茶林文化景观 | CN2_FOLK_002 | 民族与民俗文化 | 云南省 | medium | 0 | 20 |
| 25 | P2 | 左江花山岩画文化景观 | CN2_FOLK_005 | 民族与民俗文化 | 广西壮族自治区 | medium | 3 | 19 |
| 26 | P2 | 登封“天地之中”历史古迹 | CN2_ANCIENT_007 | 古城与历史文化 | 河南省 | medium | 3 | 9 |
| 27 | P3 | 土司遗址 | CN2_ANCIENT_018 | 古城与历史文化 | 跨省 | low | 3 | 11 |
| 28 | P3 | 周口店北京人遗址 | CN2_ANCIENT_013 | 古城与历史文化 | 北京市 | low | 3 | 7 |
| 29 | P3 | 元上都遗址 | CN2_ANCIENT_014 | 古城与历史文化 | 内蒙古自治区 | low | 3 | 7 |

## 8. 生成文件清单

| 文件 | 说明 |
|---|---|
| `docs/china_heritaqa_dataset_audit.md` | 数据集审计报告 |
| `docs/china_heritaqa_kb_expansion_report.md` | 本报告 |
| `data/knowledge_base/chinese_cultural_symbols_v2_candidates.csv` | v2 候选表（39 条：29 new + 10 existing） |
| `data/knowledge_base/chinese_cultural_symbols_v2_candidates.json` | 同上（JSON，含全部字段） |
| `data/knowledge_base/chinese_cultural_symbols_v2.csv` | 正式 KB v2（114 条，UTF-8 CSV） |
| `data/knowledge_base/chinese_cultural_symbols_v2.json` | 正式 KB v2（114 条，含元信息与 provenance） |
| `data/knowledge_base/reference_images_manifest_v2.json` | 参考图 provenance 清单 |
| `data/knowledge_base/reference_images_v2/` | 参考图本地文件（下载池） |
| `data/china_heritaqa/meta/` | ChinaHeritaQA 元数据原始副本 |
| `data/china_heritaqa/qa/` | q1–q7 问答原始副本 |
| `data/china_heritaqa/official/ncha_world_cultural.json` | 国家文物局世界文化遗产名录索引 |
| `data/china_heritaqa/candidate_stats.json` | 候选统计中间结果 |
| `data/china_heritaqa/reference_image_qc.json` | 图片质量检查明细 |
| `scripts/build_kb_v2_candidates.py` | 候选生成脚本（含人工核对映射表） |
| `scripts/collect_reference_images_v2.py` | 参考图收集与 QC 脚本 |
| `scripts/make_kb_v2_reports.py` | 本报告生成脚本 |
| `scripts/merge_kb_v2.py` | 正式 KB v2 合并脚本（含复合遗产拆分） |

## 9. 本轮未做 / 已确认后的执行

- 未运行 Text / Image / Multimodal 消融实验，未运行 Identity Gate，未调用 GLM；
- 未修改 `src/`、`experiments/`、v1 KB、v1 manifest；
- 已按确认执行正式 KB v2 合并：复合遗产拆分，全部 29 个新候选入库（含 low 的 3 条），详见第 10 节；
- 沈阳故宫、大昭寺、罗布林卡等子项仍未单独建符号，留待后续评估。

## 10. 正式 KB v2 合并结果

执行脚本 `scripts/merge_kb_v2.py`，输出 `data/knowledge_base/chinese_cultural_symbols_v2.csv/.json`（v1 文件未改动）。

| 项目 | 结果 |
|---|---|
| v1 符号 | 62 |
| ChinaHeritaQA 驱动新增 | 33（29 个候选中 3 个复合遗产拆为 7 个子符号：-3 +7） |
| **合计** | **95** |
| review_status | 新增 33 条已由用户确认，全部 `approved`（2026-10-27）；v1 保持原状态 |
| 五维分布（主维度） | ANCIENT 41 / RED 12 / FOLK 18 / TECH 12 / MODERN 12 |
| 新增可识别性 | high 23 / medium 7 / low 3 |
| v1 可识别性 | v1 无该字段，合并后统一标为 `not_evaluated`（未评估，不臆造） |
| 新增有参考图 | 32 / 33（景迈山仍缺） |

复合遗产拆分映射：

| 母项（候选） | 子符号 | 可识别性 |
|---|---|---|
| CN2_ANCIENT_019 峨眉山—乐山大佛 | CN2_ANCIENT_023 峨眉山 / CN2_ANCIENT_024 乐山大佛 | high / high |
| CN2_ANCIENT_010 青城山—都江堰 | CN2_ANCIENT_025 青城山 / CN2_ANCIENT_026 都江堰 | high / high |
| CN2_ANCIENT_016 曲阜孔庙、孔林和孔府 | CN2_ANCIENT_027 曲阜孔庙 / CN2_ANCIENT_028 曲阜孔林 / CN2_ANCIENT_029 曲阜孔府 | high / medium / medium |

子符号继承母项的官方来源页、参考图与 q1 样本归属（`china_heritaqa_origin` 追加 `::split`），母项不再单独入库。
`SymbolKnowledgeBase` 默认路径已切换到 v2，v1 仍可通过显式路径加载。

在上述 95 条基础上，又追加用户指定的科技与创新文化补充 19 条（第 11 节），**v2 最终 114 条**。

## 11. 科技与创新文化（TECH）补充入库

用户提供 27 个名称，其中 4 个是同一实体的重标/处理后素材名，归一化后去重，得到 23 个唯一实体：

| 清单原名 | 归一化结果 | 处理 |
|---|---|---|
| 北大(重标) | 北京大学 | 命中 v1 `BJ_INNOV_006`，不新建 |
| 首钢园-多镜头拼接-突变(处理后) | 首钢园 | 命中 v1 `BJ_FASHION_006`，不新建 |
| 清华大学多镜头拼接(处理后) | 清华大学 | 命中 v1 `BJ_INNOV_007`，不新建 |
| 中关村国际创新中心(重标) | 中关村国际创新中心 | 新建 `CN2_TECH_006`，重标名写入 notes |

其余命中 v1 的还有“未来科学城”（`BJ_INNOV_008`）。最终新增 19 条，`symbol_id=CN2_TECH_001…019`，主维度统一为 TECH：

| symbol_id | 规范名 | 可识别性 | 类型 | 地域 |
|---|---|---|---|---|
| CN2_TECH_001 | 中国科学院大学 | medium | 高等学府 | 北京市怀柔区 |
| CN2_TECH_002 | 中国工程院 | low | 科研机构 | 北京市西城区 |
| CN2_TECH_003 | 中关村生命科学园 | medium | 科技园区 | 北京市昌平区 |
| CN2_TECH_004 | 中关村软件园 | medium | 科技园区 | 北京市海淀区 |
| CN2_TECH_005 | 中关村国家自主创新示范区展示中心 | high | 科技展馆 | 北京市海淀区 |
| CN2_TECH_006 | 中关村国际创新中心 | high | 科技会展中心 | 北京市海淀区 |
| CN2_TECH_007 | 中关村广场 | medium | 城市广场 | 北京市海淀区 |
| CN2_TECH_008 | 中关村壹号（清单写“中关村1号”） | high | 科技商务综合体 | 北京市海淀区 |
| CN2_TECH_009 | 中关村（亦庄）国际机器人产业园 | medium | 产业园区 | 北京市大兴区（经开区） |
| CN2_TECH_010 | 中钢国际广场 | high | 商务楼宇 | 北京市海淀区 |
| CN2_TECH_011 | 雄安新区中关村科技园 | medium | 科技园区 | 河北省雄安新区 |
| CN2_TECH_012 | 集成电路产业园 | low | 产业园区 | 北京市大兴区（经开区） |
| CN2_TECH_013 | 怀柔科学城 | medium | 科学城 | 北京市怀柔区 |
| CN2_TECH_014 | 国际创投集聚区 | low | 科技服务街区 | 北京市海淀区 |
| CN2_TECH_015 | 东升科技园 | medium | 科技园区 | 北京市海淀区 |
| CN2_TECH_016 | 北京量子信息科学研究院 | low | 科研机构 | 北京市海淀区 |
| CN2_TECH_017 | 北京理工大学 | high | 高等学府 | 北京市海淀区 |
| CN2_TECH_018 | 北京经济技术开发区（亦庄） | medium | 产业新城 | 北京市大兴区 |
| CN2_TECH_019 | 北京航空航天大学 | high | 高等学府 | 北京市海淀区 |

说明：

- `review_status=approved`（用户于 2026-10-27 全部确认），`source_type=user_provided`，官方来源与参考图尚未核验（`source_url` 留空，不臆造链接）；
- 名称粒度较泛的“集成电路产业园”“国际创投集聚区”已写入 notes，需后续确认具体园区/街区范围；
- v2 维度分布（按主维度）：ANCIENT 41 / RED 12 / FOLK 18 / TECH 31 / MODERN 12，合计 114。
