# 创新点1：EMCAST描述策略与文化视频评价

- `t2v_cultural_taskset/taskset_candidates_v1.json`：历史候选方案。
- `t2v_cultural_taskset/eval_batch1_input_v*.json`：第一批评价输入版本，正式任务为T02/T03/T05/T08/T09。
- `t2v_cultural_taskset/batch2_v1/`：第二批T01/T04/T06/T07/T10任务、20份提示词、20项事实。
- `t2v_cultural_taskset/human_eval/`：人工评价。
- `t2v_cultural_taskset/vbench_test/`：VBench记录。
- `t2v_cultural_taskset/reference_images/`：补充参考图。
- `videos/batch1/`：第一批20条生成视频。

第二批事实与参考图的待审核状态保持不变。JSON中的项目相对路径以CulturalVideoAnnotation为根，prompt_file仍相对所在batch2_v1目录。

## 当前执行入口（四组修订）

使用[`four_group_v2/README.md`](four_group_v2/README.md)与`python scripts/innovation1/four_group_pipeline.py audit`。新方案仅G1—G4，人工冻结后生成；历史文件保留原身份。当前120条为计划，第二批原视频T06对象与配置不一致待确认。
