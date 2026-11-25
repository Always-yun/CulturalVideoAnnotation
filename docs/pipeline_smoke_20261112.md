# EMCAST主管线与创新点2合并验证

2026-11-12，用 `data/test/鸟巢.mp4` 做真实GLM API试跑。原始主管线成功输出完整E/M/C/A/S/T及TXT/JSON；文化增强链路同样成功，文化链路耗时约73秒。

默认主入口现在启用：视觉描述 → CLIP/关键词多模态Top-K → Confidence Gate → EMCAST闭集受控标注 → Identity Verifier v2。知识库沿用创新点2的v2，可通过 `--kb-path` 显式更换。

Top-1为鸟巢，Confidence Gate为confident，v2判定accept_exact_identity，无额外LLM核验调用。最终标注、TXT、JSON及pipeline_trace一致；T层确认来自元数据（3840×2160，60 FPS，6.45秒）。初次集成试跑发现T层函数名错误，修正后重新跑通。

修正了既有文化管线中门控只改解析字段、未同步最终正文的问题；闭集约束检查全部输出实体，不能因一个符号命中而放行其余错误符号。保留raw_final_annotation供追溯。

```bash
# 默认完整文化增强
python scripts/run_annotation.py --video data/test/鸟巢.mp4

# 原始EMCAST对照
python scripts/run_annotation.py --video data/test/鸟巢.mp4 --culture-mode off

# 回归测试
python -m unittest discover -s tests -v
```

6项回归测试通过，覆盖主管线分发、自定义提示词绕过RAG、闭集混入未知符号、拒识改写与保存一致性、v2接受/拒绝和多GPU参数透传。Python源码编译检查与两个CLI帮助入口通过。未试跑本地Qwen、真实多GPU并发或全量数据。

原始结果位于 `outputs/smoke_pipeline_baseline/`，合并结果与日志位于 `outputs/smoke_pipeline_integrated/`；具体路径见 [机器记录](pipeline_smoke_20261112.json)。
