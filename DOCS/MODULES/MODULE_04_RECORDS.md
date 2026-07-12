# 模块 04：记录与收尾

## 职责

- 启动时创建本次 `RUN_ID`、正式运行目录和 `run/started` 首条事件；本模块是 RUN_ID 与记录规则的唯一事实源。
- 刷新 `RUN_ID-run-record.jsonl` 和 `RUN_ID-run-record.md`，不把本次状态作为下次默认续跑依据。
- 记录本次随机选中的固定环境图路径和正式视频路径。`xdy` 记录固定角色代理图、首中尾视频代理图，以及胸部体量是否明显偏小的质检结论；`xdysp` 不要求代理图，质检状态记录为 `not_performed` 并注明由用户本人检查。
- 只要正式视频已经生成，就记录 Google Drive 根目录上传状态；成功时记录文件名、文件 ID 或 URL 等可用返回信息，失败时记录原因和是否需要补传。
- 已尝试发布时，补充抖音、快手和整体结论及报告路径；未发布时记录 `not_requested` 或 `awaiting_confirmation`。

## 启动建档

```bash
RUN_SOURCE="${RUN_SOURCE:-manual}"
RUN_ID="$(.venv/bin/python TOOLS/run_workspace.py init --source "$RUN_SOURCE" --format id)"
```

`init` 按 `Asia/Shanghai` 时间原子创建 `TEMP/RUN_ID/logs/` 和 `OUTPUT/`，并向 `TEMP/RUN_ID/RUN_ID-run-record.jsonl` 写入 `run/started` 首条事件。RUN_ID 唯一合法格式为 `YYYYMMDD-HHMMSS`；同一秒内首个运行使用纯时间，后续依次追加 `-01` 至 `-99`。主题、模式、来源、定时任务、补跑或 Codex thread 标识通过 `--source` 和 `--data` 写入事件，不得写入 RUN_ID。

后续所有 prompt、下载、代理图、发布报告和运行记录都使用本次 RUN_ID，不从旧目录推断本次状态。`TEMP/` 是可清理的过程目录，不作为下次默认续跑状态；正式运行目录固定为 `TEMP/RUN_ID/`，正式成片固定为 `OUTPUT/RUN_ID.mp4`，两者必须使用完全相同的 RUN_ID。

## 命令

```bash
python3 TOOLS/run_record.py summary "TEMP/$RUN_ID/$RUN_ID-run-record.jsonl" --md "TEMP/$RUN_ID/$RUN_ID-run-record.md"
```

收尾摘要必须包含 Google Drive 上传状态和发布状态；已尝试发布时再写入平台报告和 `publish-both-report.json` 路径。

收尾后执行命名审计：

```bash
.venv/bin/python TOOLS/run_workspace.py audit
```

审计检查正式运行目录、运行记录与 `OUTPUT/*.mp4` 的命名和对应关系；候选、调试、缓存、`TEMP/del/` 及其他辅助目录不作为正式 RUN_ID。
