# 模块 04：记录与收尾

## 职责

- 启动时按 `DOCS/PROJECT.md` 的“运行建档”创建本次 `RUN_ID`、目录和首条事件。
- 刷新 `RUN_ID-run-record.jsonl` 和 `RUN_ID-run-record.md`，不把本次状态作为下次默认续跑依据。
- 记录正式视频路径、固定角色代理图、首中尾视频代理图，以及人脸身份和身材比例两项人工质检结论；其他画面差异按需记 warning。
- 已尝试发布时，补充抖音、快手和整体结论及报告路径；未发布时记录 `not_requested` 或 `awaiting_confirmation`。

## 启动建档

```bash
RUN_ID="$(date +%Y%m%d-%H%M%S)"
mkdir -p "TEMP/$RUN_ID/logs" OUTPUT
.venv/bin/python TOOLS/run_record.py append "TEMP/$RUN_ID/$RUN_ID-run-record.jsonl" \
  --stage run \
  --event started \
  --status in_progress \
  --summary "本次运行已建档"
```

同一秒内存在并发任务时，为后启动任务的 `RUN_ID` 追加来源或序号后缀。定时任务、补跑或 Codex thread 标识可用时，通过 `--data` 写入首条事件。

## 命令

```bash
python3 TOOLS/run_record.py summary TEMP/RUN_ID/RUN_ID-run-record.jsonl --md TEMP/RUN_ID/RUN_ID-run-record.md
```

收尾摘要必须包含发布状态；已尝试发布时再写入平台报告和 `publish-both-report.json` 路径。
