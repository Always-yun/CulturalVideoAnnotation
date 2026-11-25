# 两个创新点与应用层进度核查

核查日期：2026-11-12。只统计本地已保存产物；未重跑模型。旧版本、补跑和同视频多模式结果不重复计为新增素材。不设置缺乏验收分母的整体完成百分比。

## 创新点1：EMCAST描述策略与文化视频生成评价

- 正式方案共两批10个任务，按每任务G1–G4各1条视频计算，目标40条。
- 第一批视频20/20已存在；第二批本实验目录尚无生成视频，按当前方案合计20/40（50%）。第二批已保存5个任务、20份提示词、20项事实；事实与参考图待核对冻结。
- 第一批局部文化事实机器评价：16/20条视频、64/80项事实已有结果；T08的4条视频16项评分因F4标准待核实未完成。T02另有v3重评16项，用于替换旧标准结果，不能叠加成新增事实。
- 第一批整体形态评价20/20；CMA/TWA20/20；VBench成像质量和主体一致性20/20，未运行其余14维。
- 人工评价表3份，每份160行，评分栏均为空，即0/480项人工评分已回填。
- G1–G4映射仍为unverified；生成模型、种子等记录待补；T02旧/新标准结果尚须统一成最终汇总口径。

依据：`experiments/innovation1/t2v_cultural_taskset/`下的`batch1_machine_eval_merged_v1.json`、`T02_eval_v3_results.json`、`exp3_cma_twa_eval_v1.json`、`vbench_test/batch1_iq_sc_summary.json`、`human_eval/scoring_sheet_rater*.csv`与`batch2_v1/`。

## 创新点2：文化知识增强与身份核验

- v2知识库114条，其中88条有参考图记录；v3知识库126条，其中88条有参考图记录。图片记录存在不等于人工核验通过。当前主入口默认仍用v2。
- 正式评测31条：Known27、Hard Unknown3、Easy Unknown1。
- 基础五模式实验155条运行记录（31×5）；Identity Gate v1四种KB模式124条（31×4）；图像修正补跑各93条，只替换相应模式，不与基础运行相加作独立素材。
- 最终比较表`final30_predictions.csv`有310行，即31×5×2种方法展示口径，包含复用Free及修正后选择的结果，不等于310条独立视频或310次新增调用。
- v2身份核验最终结果31/31已保存，沿用multimodal_controlled检索和标注结果，并非再跑完整五模式。
- v2视频级Known准确率19/27=70.37%；Hard Unknown拒识3/3；Easy Unknown拒识1/1；Known误拒7/27=25.93%。Unknown样本仅4条，不能据此声称大规模泛化已验证。
- 尚需统一最终论文表格与统计口径；修复缺失素材；补充更充分的Unknown样本与人工审核。近期主入口闭集约束及正文同步逻辑有修正，旧31条结果未按新入口全量重跑。

依据：`experiments/innovation2/results/cultural_rag/final30/`、`final31/`与`runs/cultural_ablation/`。`docs/innovation2/innovation2_current_status.md`是10月17日历史状态，含旧知识库与“门控未实现”等内容，不代表11月12日现状。

## 应用层：自动标注入口与标注资产

- 命令行主入口已合并多模态检索、Confidence Gate、受控标注、Identity Verifier v2，T层按元数据确定性写入；单视频与批量入口已接通，文化参数可透传到多GPU入口。
- 真实端到端验收：鸟巢1条视频，原始版与文化增强版各成功运行一次，均保存完整六维TXT/JSON；增强文化链路约73秒。6项回归测试通过。
- 本地Qwen推理、真实多GPU并发、文化增强版全量批处理未验收；当前证据只支持GLM API单样本流程可运行。
- Label Studio导出有74条六维模型预标注，视频引用去重73个；全部有predictions，无annotations字段回填记录，即此导出中0条已人工审核。引用去重不等于按视频内容哈希去重，也不证明当前所有源视频可访问。
- 历史基础输出目录有22份JSON、28份TXT，JSON中10个不同源路径标识，21份包含完整六维标题；包含多次运行和历史格式，不能作为22个独立视频的正式验收数量。
- 新合并的文化增强版本没有证据显示已完成74条预标注的批量升级，不能把旧预标注计入新版本的完成量。

依据：`docs/pipeline_smoke_20261112.json`、`outputs/smoke_pipeline_baseline/`、`outputs/smoke_pipeline_integrated/`、`outputs/annotations/`、`experiments/innovation2/data/label_studio_exports/P-LS.json`。

## 后续收尾顺序

1. 创新点1先冻结第二批事实与参考图，再生成20条视频；确认组别/参数、补T08局部事实评价并统一T02 v3汇总，开展人工评分。
2. 创新点2以final31 v2作为身份核验结果入口，统一与final30五模式表的口径，补齐缺失素材及最终人工审计。
3. 应用层选择不与实验测试混淆的验收样本集，用当前合并版本批量自动标注，记录失败与耗时，并完成代表性样本人工验收。
