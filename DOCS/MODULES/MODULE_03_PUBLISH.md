# 模块 03：双平台发布

## 职责与前置条件

将本次 `OUTPUT/RUN_ID.mp4` 同步发布到抖音和快手，设置 `内容由AI生成`，填写文案与标签，并记录单平台和整体结果。

- 模块 02 已通过：正式 MP4 可解码，两项内容硬门通过；用户要求确认或暂停时已取得明确发布授权。
- 只处理本次 `RUN_ID`，不因 `TEMP/` 或 `OUTPUT/` 中存在旧文件而选用旧成片。
- 默认跳过模块 00；helper 在动作现场检查 CDP、Playwright、页面和登录态，出现环境问题时再进入模块 00。
- 不设置按日期、轮次或条数的发布上限。仅当 scheduled run/thread、`RUN_ID`、成片路径和平台均相同，且该平台已返回 `published` 时，才跳过再次点击该平台发布按钮。

## 执行入口

`TOOLS/publish_adapter.py both` 固定先抖音、后快手；抖音失败也继续尝试快手。标签先从 `MATERIAL/publish-tag-pool.json` 生成候选，再选择与人物、场景、动作和穿搭一致的四个。

```bash
python3 TOOLS/publish_tag_pool.py --count 4 --shell-args

.venv/bin/python TOOLS/publish_adapter.py both OUTPUT/RUN_ID.mp4 \
  --title "作品标题" \
  --description "与本次成片一致的作品简介" \
  --tag "标签1" \
  --tag "标签2" \
  --tag "标签3" \
  --tag "标签4" \
  --no-location \
  --cdp-url http://127.0.0.1:9222 \
  --out-dir TEMP/RUN_ID/logs/publish \
  --record-jsonl TEMP/RUN_ID/RUN_ID-run-record.jsonl
```

## 发布要求

- 标题必须来自本次画面、场景或穿搭品类；简介使用正常文案，话题统一通过 `--tag` 传入。
- 默认不填写发布地址。抖音仅在显式传入 `--location` 且未传 `--no-location` 时尝试位置，失败只记 warning；快手兼容位置参数但固定跳过地址设置。
- 抖音默认使用视频中间帧封面和 `--upload-mode cdp`，不等待 AI 智能推荐封面，也不主动切换 `auto`、`dialog` 或 `--current-tab`。
- 快手必须使用常规视频入口；进入 VR360° 模式时阻断。上传或转码尚未完成时等待，不提前点击发布。
- 两个平台都必须完成 `内容由AI生成` 声明后才能点击发布。
- 报告写入 `TEMP/RUN_ID/logs/publish/` 下的 `douyin-publish-report`、`kuaishou-publish-report` 和 `publish-both-report`，同时生成 JSON 与 Markdown。

## 成功判定

- 两个平台均返回 `published` 且聚合报告为 `published`，整体才算成功；发布后无需核对创作者中心内容列表。
- 任一平台失败不回滚另一平台，也不阻断另一平台尝试。单个平台已经成功时，后续只重试未成功平台。
- AI 声明、上传完成状态、发布按钮或 helper 执行任一项失败时，记录该平台失败及原因。
