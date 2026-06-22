# 模块 05：记录与收尾

## 职责

- 刷新 `RUN_ID-run-record.jsonl` 和 `RUN_ID-run-record.md`。
- 成功生成正式视频后记录参考去重账本。
- 发布成功后补充发布状态。
- 不把本次任务状态作为下次默认续跑依据。

## 命令

```bash
python3 TOOLS/reference_dedupe.py record "REFERENCE_URL" --route anna --status used
python3 TOOLS/reference_dedupe.py record "REFERENCE_URL" --route anna --status published
python3 TOOLS/run_record.py summary TEMP/RUN_ID/RUN_ID-run-record.jsonl --md TEMP/RUN_ID/RUN_ID-run-record.md
```
