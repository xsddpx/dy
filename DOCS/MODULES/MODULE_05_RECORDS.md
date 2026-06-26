# 模块 05：记录与收尾

## 职责

- 刷新 `RUN_ID-run-record.jsonl` 和 `RUN_ID-run-record.md`。
- 成功生成正式视频后记录参考去重账本。
- 发布成功后补充运行记录中的发布状态。
- 为后续运营复盘保留可归类字段，但不要求每次发布后立即读取作品表现。
- 不把本次任务状态作为下次默认续跑依据。

## 建议记录字段

发布成功后，如页面或运行上下文可得，优先在运行记录或发布报告中保留以下字段：

- `published_url`
- `publish_time`
- `title`
- `description`
- `tags`
- `reference_url`
- `reference_video_id`
- `content_type`
- `scene_type`
- `outfit_keyword`
- `hook_action`
- `duration_sec`
- `ai_generated_declaration`

运营复盘阶段如读取到作品表现，再追加或单独记录以下指标：

- `play_count`
- `like_count`
- `comment_count`
- `share_count`
- `favorite_count`
- `average_play_duration`
- `completion_rate_5s`
- `bounce_rate_2s`
- `cover_click_ratio`
- `follower_count`
- `follower_delta`

指标缺失时保留为空或不记录，不得用估算值补齐。

## 命令

```bash
python3 TOOLS/reference_dedupe.py record "REFERENCE_URL" --route anna --status used
python3 TOOLS/run_record.py summary TEMP/RUN_ID/RUN_ID-run-record.jsonl --md TEMP/RUN_ID/RUN_ID-run-record.md
```
