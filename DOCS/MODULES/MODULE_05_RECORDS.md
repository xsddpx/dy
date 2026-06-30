# 模块 05：记录与收尾

## 职责

- 刷新 `RUN_ID-run-record.jsonl` 和 `RUN_ID-run-record.md`。
- 成功生成正式视频后记录产物和关键执行结果。
- 发布后补充运行记录中的抖音、快手和整体发布状态。
- 不把本次任务状态作为下次默认续跑依据。

## 命令

```bash
python3 TOOLS/run_record.py summary TEMP/RUN_ID/RUN_ID-run-record.jsonl --md TEMP/RUN_ID/RUN_ID-run-record.md
```

发布收尾摘要必须包含：

- 抖音发布结论和报告路径。
- 快手发布结论和报告路径。
- 双平台整体结论和 `publish-both-report.json` 路径。
