# ChinaHeritaQA 数据集审计报告

- 审计日期：2026-10-27
- 数据来源：官方仓库 `https://github.com/boleima/ChinaHeritaQA`（论文 arXiv:2606.08959）
- 本地落盘：`data/china_heritaqa/meta/`（元数据）、`data/china_heritaqa/qa/`（问答）、`data/china_heritaqa/official/`（官方核验索引）
- 审计方式：直接读取仓库原始 JSON 与 git 文件树，未依据 README 推断

## 1. 结论摘要

| 项目 | 实测值 |
|---|---|
| 世界遗产实体（站点）数量 | **51** |
| 遗产类型分布 | 文化 35 / 自然 12 / 双遗产 4 |
| 图像数量 | **2279**（元数据 `Number of Images` 与问答 `img_url` 去重后一致） |
| 问答数量 | **14133**（q1–q7 七类） |
| 是否有明确遗产实体名 | 有（`Name.cn` / `Name.en`，51 个 UNESCO 站点级名称） |
| 是否有地点/省市信息 | 有（`City.cn` / `City.en`，如“湖北省丹江口市”“北京市”） |
| 是否有类别/遗产类型 | 有（`Type.cn`：文化/自然/混合） |
| 是否有图片路径 | 有（问答 `img_url`，如 `./Image_data\\Dazu_Rock_Carvings\\xxx.jpg`；元数据 `Image URLs`） |
| 是否随仓库提供完整图像 | **否**。仓库仅含 23 个样例图文件（`Image_data` 13 张 + `worlds_data` 10 张），2279 张图像只给出微博图床相对路径 |
| 是否有描述文本 | 有（`Brief_intro` / `Description` / `Standard` / `History_background` / `Main_function` / `BUilding_use`） |
| 是否有官方来源字段 | **无**。元数据不含 source_url / 来源机构 / 许可证字段，官方来源需本轮另行核验 |
| 是否存在中英文名称 | 有（`Name`、`City`、`Type`、`Dynast` 等字段均为 cn/en 双语） |

## 2. 真实数据结构

### 2.1 元数据 `DATA/heritage_meta_weibo_V1.json`（51 条）

每条字段：

| 字段 | 类型 | 说明 | 示例 |
|---|---|---|---|
| `Name` | dict{cn,en} | 遗产地规范名 | 武当山古建筑群 / Ancient Building Complex in the Wudang Mountains |
| `City` | dict{cn,en} | 所在省市 | 湖北省丹江口市 / Danjiangkou, Hubei |
| `Dynast` | dict{cn,en} | 朝代 | 明 |
| `Type` | dict{cn,en} | 文化/自然/混合 | 文化 |
| `History_background` | dict{cn,en} | 历史背景长文本 | — |
| `Main_function` / `BUilding_use` | dict{cn,en} | 主要功能 / 建筑用途 | — |
| `Brief_intro` / `Description` / `Standard` | dict{cn,en} | 简要介绍 / 描述 / 价值标准 | — |
| `Number of Images` | int | 该站点图像数 | 183（武当山） |
| `Image URLs` | list | 微博图床相对路径 | `./Image_data\\...\\xxx.jpg` |

补充：`DATA/heritage_brief_intro.json` 有 **58** 条，比站点表多 7 条
（Ancient_Villages_in_Southern_Anhui_Xidi_and_Hongcun, Lushan_National_Park, Silk_Roads_the_Routes_Network_of_Chang_an_Tianshan_Corridor, The_Grand_Canal, Yin_Xu, Jiuzhaigou_Valley_Scenic_and_Historic_Interest_Area, Three_Parallel_Rivers_of_Yunnan_Protected_Areas），
涉及皖南古村落、庐山、丝绸之路、大运河、殷墟、九寨沟、三江并流——**这 7 条不含 `City/Type/图像` 等元数据，未纳入实体提取**。

### 2.2 问答 `DATA/quesion_info/q1–q7.json`（14133 条）

结构：`{question_info: {question_type, question_content, is_img_in_question, options_INFO:[...]}}`
每个样本含 `index`、`img_url`、`options`（固定 5 项，中文/英文各一，含 `is_true` 标记）。

| 文件 | 认知维度 | 数量 | 是否以图为主 |
|---|---|---|---|
| q1 | 名称识别（图片→遗产地） | 2279 | 是 |
| q2 | 地点识别（遗产地→图片） | 2279 | 否（给名称猜图） |
| q3 | 简要介绍 | 2279 | 是 |
| q4 | 朝代判定 | 1658 | 是 |
| q5 | 历史背景 | 1989 | 是 |
| q6 | 主要功能 | 2279 | 是 |
| q7 | 建筑用途 | 1370 | 是 |
| **合计** | — | **14133** | — |

### 2.3 图像可得性（重要）

- `Number of Images` 合计 **2279**，与 q1 的 2279 个唯一 `img_url` 一致；
- 图像实际位于微博图床，仓库只提交了 23 个样例文件，**无法从仓库直接获得 2279 张原图**；
- 因此本轮 KB 参考图**不取自 ChinaHeritaQA**，统一改用国家文物局等官方页面（见扩充报告第五节）。

### 2.4 实体粒度

- ChinaHeritaQA 的实体是 **UNESCO 站点级**（51 个），不是构件级；
- 复合遗产（峨眉山—乐山大佛、青城山—都江堰、曲阜三孔、明清皇家陵寝）在数据中作为**一个实体**出现；
- 子项（如沈阳故宫、大昭寺、少林寺、乐山大佛）只在描述文本中出现，**没有独立实体 ID 与独立图像集合**。

### 2.5 地点与图像分布

- 图像数最多：大足石刻(313)、黄龙风景名胜区(195)、武当山古建筑群(183)、云岗石窟(178)、龙门石窟(132)
- 图像数最少：承德避暑山庄及其周围寺庙(2)、武夷山(1)、四川大熊猫栖息地(1)
- 自然遗产 12 项：巴丹吉林沙漠——沙山湖泊群、中国丹霞、梵净山、黄龙风景名胜区、湖北神农架、中国黄（渤）海候鸟栖息地（第二期）、三清山国家公园、可可西里、四川大熊猫栖息地、中国南方喀斯特、武陵源风景名胜区、天山山脉

## 3. 对知识库扩充的影响

1. 可提取的“实体”上限为 51 个站点，其中文化 35、双遗产 4（可归入文化维度）、自然 12（不属文化符号）；
2. 数据无官方来源字段，`source_url/source_organization/source_authority_level/source_status` 全部由本轮核验补齐；
3. 数据集无构件级实体，若后续需要“乐山大佛”“少林寺”“沈阳故宫”等细粒度符号，必须另行补充来源，不能声称来自 ChinaHeritaQA；
4. 图像不可直接复用，参考图必须独立收集并记录 provenance。
