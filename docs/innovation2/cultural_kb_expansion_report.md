# 中华文化知识库全国扩展报告

日期：2026-10-17

本轮扩展保留原有47个北京符号及其稳定 `symbol_id`，在同一份知识库中新增15个全国条目，未建立平行知识库。合并后的 `data/knowledge_base/chinese_cultural_symbols_v1.json` 共62条。

## 覆盖统计

| 项目 | 数量 |
|---|---:|
| 原有北京样本 | 47 |
| 新增非北京条目 | 15 |
| 去重符号总数 | 62 |
| 省级区域覆盖（新增条目） | 10 |
| 已采集待人工复核的图片候选 | 60 |
| 有图片候选的符号 | 56 |

新增省级区域为陕西、甘肃、西藏、浙江、山西、贵州、河北、广东、海南、福建。按五个文化维度统计（多标签重复计数）：ANCIENT 15、RED 12、FOLK 13、TECH 12、MODERN 14。北京历史样本占全部条目的72.58%，非北京扩展条目占24.19%；维度重复计数不用于计算符号总数。

## 新增条目

| 维度 | 符号 |
|---|---|
| ANCIENT | 秦始皇帝陵兵马俑、敦煌莫高窟、布达拉宫、良渚古城遗址、云冈石窟 |
| RED | 遵义会议会址、西柏坡纪念馆、延安革命纪念馆 |
| FOLK | 粤剧、藏族唐卡（勉唐画派）、侗族大歌 |
| TECH | 中国天眼（FAST）、文昌航天发射场 |
| MODERN | 杭州西湖文化景观、泉州：宋元中国的世界海洋商贸中心 |

`侗族大歌`目前为 `draft`，因为本轮只找到国家级非遗平台入口，尚未补齐项目专页；它不进入正式评测集。其余新增条目为 `reviewed`，后续仍可由人工专家复核。

## 来源与图片规则

来源白名单位于 `config/cultural_source_policy.json`。新增条目的 `source_records` 保存来源名称、URL、权威等级、机构、访问日期和简短事实证据。当前样本优先使用文化和旅游部、国家文物局、国家发展改革委、中国载人航天官方网站、中国非物质文化遗产网和省市政府/文物/文旅机构页面。百度百科只作为 `image_only` 图片候选来源，不能写入文化事实或提升事实来源等级。

图片由 `scripts/collect_cultural_reference_images.py` 从已登记的官方来源页面发现，再下载页面中的原始图片URL；每条记录同时保存 `source_page_url`、`image_url`、本地路径、机构、权威等级、访问日期、内容类型和 SHA-256。采集器拒绝非白名单来源、搜索缩略图、站点图标、二维码和最小边长小于200像素的图片。未发现合格原图的条目保持 `reference_images=[]`，不会用文本相似度冒充图像证据。

图片复核清单导出在 `data/knowledge_base/reference_image_review.csv`。其中 `human_review` 和 `review_notes` 为空，只有人工确认后才应把 `use_for_retrieval` 改为 `true`。

当前保留60张图片候选，其中北京历史样本47张、全国扩展条目13张，来源包含官方页面和百度百科头图。所有候选统一标记为 `candidate_unreviewed`，并设置 `use_for_retrieval=false`；人工确认图片确实展示目标实体、为实拍且不是海报/拼贴/手绘后才可启用。已发现的拼贴、会议现场、标识图和非实拍图已直接删除。

## 可复现命令

```bash
cd /data/data/xzy/CulturalVideoAnnotation
python3 scripts/extend_chinese_kb.py
python3 scripts/collect_cultural_reference_images.py --dry-run --ids CN_ANCIENT_003
python3 scripts/collect_cultural_reference_images.py --ids CN_ANCIENT_003
```

`scripts/build_chinese_kb.py` 仍保留用于生成历史47条基础数据，但检测到已扩展知识库时会拒绝覆盖；全国扩展统一使用 `extend_chinese_kb.py`。
