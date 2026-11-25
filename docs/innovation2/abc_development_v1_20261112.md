# A/B/C统一开发对照入口

实验已启动：30条视频，A/B/C三组，共90组结果。基础调用约150次GLM请求，另有按需文字转录及身份核验；三路并发。

[自动更新的实验报告](../../experiments/innovation2/results/abc_development_v1/report.md)；[冻结清单](../../experiments/innovation2/results/abc_development_v1/manifest.json)。运行日志：`/tmp/emcast_abc_run.log`。

脚本：`scripts/innovation2/run_abc_development.py`。同一输出目录重启时跳过已经成功保存的组；代码或配置哈希变化则拒绝混合续跑。

23项回归测试通过，其中新增测试确认C复用证据时不重新请求Pass-1或文字识别。
