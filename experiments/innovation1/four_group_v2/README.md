# 创新点一：五任务四组单次生成批次

当前批次按用户于2026-11-24确认的范围执行：T01兵马俑、T04南湖红船、T06皮影戏、T07海南文昌发射场、T10东方明珠；每任务G1—G4各一次，共20条生成视频。原视频时长不作为排除或截取条件。

实验只保留四组：G1普通整段描述、G2 MiraData式结构化描述、G3文化增强整段描述、G4 EMCAST分层描述。没有Auto组。T层只在生成后从视频提取，不输入生成模型。

## 当前状态

- `protocol.json`：5任务、1次生成、20条计划；T06已从兔儿爷改为皮影戏。
- `generation_manifest.json`：20条收到的视频及哈希、分辨率、帧率、时长、编码信息。
- `received_video_inventory.csv`：便于人工查看的20条视频清单。
- `generation_checklist.csv`：文件存在与正式准入状态。
- `source_frame_inventory.csv`：5条原视频的50%预览帧与实际时间戳。
- `keyframes/`：原视频及20条生成视频的正式50%关键帧、实际PTS、视频/帧哈希和异常记录。
- `keyframe_inventory.csv`：25条视频关键帧与实际时间戳的统一清单。
- `cases_received.html`：五个任务的原视频—G1—G4实际关键帧并列预览，不作效果筛选。
- `objective_questions.csv`：共同文化问题及人工核准状态。
- `pending.json`：待补提示词核验、模型配置和原视频参考答案。

20条视频均已收到并可解码，统一为864×480、24 fps、约5.167秒。收到不等于正式准入：模型名称、种子是否支持、实际输入描述版本仍待补，因此当前`verified=0`，没有把未知信息写成已确认。

T01/T04/T07/T10暂时关联到`batch2_v1`的候选提示词及哈希，但状态仍是未冻结、待核对实际生成输入。T06仓库原文字属于兔儿爷，已从当前任务解除；旧文字备份在`history/T06_rabbit_prompts/`。T06四条皮影戏视频的实际G1—G4输入文本尚未提供，因此描述文件留空并标记`missing_actual_generation_input`，不会用新编文字冒充历史生成输入。

T06的四项客观问题根据原视频可见场景证据建立为候选：皮影人物数量、背光幕布关系、传统人物轮廓与分节肢体、同幕对向互动。它们仍需原视频模型初答和人工核准；只有画面可支持且人工确认Yes的事实才能设为必须满足项。

## 运行命令

在项目根目录运行：

```bash
cd /data/data/xzy/CulturalVideoAnnotation

# 当前批次已经执行过；仅在20条原文件未变且需要重建清单时使用
python scripts/innovation1/four_group_pipeline.py ingest-current-batch
python scripts/innovation1/four_group_pipeline.py apply-current-questions

python scripts/innovation1/four_group_pipeline.py audit
python scripts/innovation1/four_group_pipeline.py source-preview
python scripts/innovation1/four_group_pipeline.py frames
python scripts/innovation1/four_group_pipeline.py requests

# 显式调用项目既有GLM评价；先小批运行
python scripts/innovation1/four_group_pipeline.py evaluate --limit 1
python scripts/innovation1/four_group_pipeline.py reparse-machine
python scripts/innovation1/four_group_pipeline.py evaluate-video --limit 22
python scripts/innovation1/four_group_pipeline.py collect-video-results
python scripts/innovation1/four_group_pipeline.py collect-vbench
python scripts/innovation1/four_group_pipeline.py summarize-computer

# 人工核准原视频答案并补齐生成来源信息后
python scripts/innovation1/four_group_pipeline.py requests
python scripts/innovation1/four_group_pipeline.py summarize
python scripts/innovation1/four_group_pipeline.py review-pack
python scripts/innovation1/four_group_pipeline.py summarize-human
python scripts/innovation1/four_group_pipeline.py summarize-metrics

python -m unittest discover -s tests -p test_innovation1_four_group.py -v
```

`requests`生成5条原视频和20条生成视频关键帧请求，并建立T06-F3、T07-F3、T07-F4的连续视频请求。生成视频在参考答案核准前可以完成机器初评，但状态保持`provisional_pending_human_reference_and_generation_provenance`；只有原视频答案人工核准、生成来源核验通过后，才能进入正式统计。模型原始回复和解析结果分别保留，解析失败不计作No。

本批已按用户指令完成全部计算机初评：25条关键帧请求、22条连续视频/条件请求、20条VBench IQ/SC均成功解析。汇总见`computer_evaluation_report.md`和`computer_evaluation_summary.json`。生成视频结果可以先作机器初评，但正式文化视觉事实满足率仍等待`computer_reference_review.csv`中的原视频答案人工核准。

## 关键帧与评分规则

本批在生成视频接入和查看前已登记默认50%单帧规则，现在五个任务统一使用该规则。原视频和同任务G1—G4均按各自完整时长50%位置抽帧，不因原视频长短截取，也不因某组效果调整。抽帧使用FFprobe逐帧PTS和FFmpeg指定帧；黑帧定义为灰度低于8的像素超过98%，统一在目标帧前后0.1秒内搜索，仍失败则记录错误并停止该视频。

关键帧只用于文化特征、建筑/主体形态和静态场景。T06-F3“两人连续打斗”、T07-F3“点火过程”、T07-F4“连续升空”明确标为`continuous_video`，必须观看完整连续视频，不能从单帧作答；镜头运动同样使用连续视频。多帧合并规则仍保留：Yes与No冲突记Uncertain，Yes+Uncertain记Yes，No+Uncertain记No，全Uncertain记Uncertain；同一事实每视频只计一次。

南湖红船四项局部事实即使全部为Yes，也只证明生成了符合这些视觉特征的传统船只；整体文化形态仍须结合原视频/参考图独立判断，不能由四题自动推出“准确还原南湖红船”。

文化视觉事实满足率只统计人工核准为原视频可见且必须满足的事实，生成答案Yes计成功，Uncertain保留在分母且不算成功。整体文化形态报告Match/Partial/Mismatch/Uncertain分布。回答一致率只作辅助指标，不把双方Uncertain或单纯一致当成事实正确。不另造总分。

当前只有一次生成，因此任务内均值就是该条视频的结果，重复波动记`null`，不能解释为“波动为零”。五任务再等权平均。后续若增加重复次数，脚本会按`protocol.json`的`repeats`动态要求完整重复数。

## 人工评价与历史数据

AI初评和人工独立盲评分开保存。盲评表延续旧字段结构，匿名映射单独放在`human_private/`。旧20条人工评分只属于旧视频，不复制到当前20条。历史第一批视频的组别映射、不可控API抽帧和输入配置未完全核验，仍保留原身份；只有逐项满足当前描述和配置证据时才可重新登记并评价。

最终比较保持为G1与G3、G3与G4、G1与G2，并同时报告主体、场景、时间天气、镜头运动、VBench IQ和SC。`cases_received.html`展示当前实际原视频与生成关键帧，不自动挑最好样本；正式准入后`cases.html`用于人工标注表现较好和仍有偏差的真实案例。
