# 模块 04：记录与收尾

## 职责

- 刷新 `RUN_ID-run-record.jsonl` 和 `RUN_ID-run-record.md`，不把本次状态作为下次默认续跑依据。
- 记录正式视频路径、固定角色代理图、首中尾视频代理图，以及人脸身份和身材比例两项人工质检结论；其他画面差异按需记 warning。
- 发布后补充抖音、快手和双平台整体结论及报告路径。

## 命令

```bash
python3 TOOLS/run_record.py summary TEMP/RUN_ID/RUN_ID-run-record.jsonl --md TEMP/RUN_ID/RUN_ID-run-record.md
```

收尾摘要必须包含抖音、快手和整体发布结论，以及对应平台报告和 `publish-both-report.json` 路径。
