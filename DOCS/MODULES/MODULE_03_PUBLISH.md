# 模块 03：双平台发布

## 职责

- 将 `OUTPUT/RUN_ID.mp4` 同步上传到抖音和快手。
- 两个平台都设置 `自主声明/作品声明 -> 内容由AI生成`。
- 填写标题、简介和标签。
- 默认不填写发布地址；抖音和快手都跳过地址设置。
- 点击两个平台发布按钮并记录抖音、快手和整体结果。

## 前置条件

- 已完成模块 02，正式成片已保存为 `OUTPUT/RUN_ID.mp4`。
- 已满足模块 02 的确认规则：fast 已取得用户明确发布授权。
- 默认不执行模块 00；发布 helper 会在动作现场检查 CDP/Playwright、页面接管和平台登录态，遇到环境类失败时再进入模块 00 修复。
- 本模块只发布本次 `RUN_ID` 的正式成片，不因 `TEMP/` 或 `OUTPUT/` 中存在旧文件而发布旧任务。

## 执行入口

模块 03 默认使用 `TOOLS/publish_adapter.py both` 依次编排抖音和快手发布。固定顺序为先抖音、后快手；抖音失败也必须继续尝试快手。

发布标签从 `MATERIAL/publish-tag-pool.json` 随机抽取，不写 `AI生成`、`AIGC` 或 `内容由AI生成`：

```bash
python3 TOOLS/publish_tag_pool.py --count 4 --shell-args
```

跨账户执行时必须使用固定账户环境：

```bash
sudo -H -u xsddpx python3 TOOLS/publish_adapter.py both OUTPUT/RUN_ID.mp4 \
  --title "作品标题" \
  --description "作品简介，可包含话题标签" \
  --tag "标签1" \
  --tag "标签2" \
  --tag "标签3" \
  --tag "标签4" \
  --no-location \
  --cdp-url http://127.0.0.1:9222 \
  --out-dir TEMP/RUN_ID/logs/publish \
  --record-jsonl TEMP/RUN_ID/RUN_ID-run-record.jsonl
```

要求：

- `--title` 必填且不能为空；标题应来自本次画面、场景或穿搭品类，避免只写“今日穿搭”“随拍”等泛化标题。
- 标签使用 tag 池随机抽取 4 个。
- 默认不填写发布地址；`TOOLS/publish_adapter.py both` 会在未显式传入 `--location` 时补 `--no-location`。
- 抖音 helper 只在显式传入 `--location "城市 大概地点"` 且未传 `--no-location` 时尝试设置位置；位置失败仍只记录 warning，不作为发布硬阻断。
- 快手 helper 为兼容双平台入口会接受 `--location` / `--no-location` / `--location-timeout`，但固定跳过地址设置，不产生位置 warning。
- 抖音 helper 默认使用视频中间帧作为封面，不等待或应用主发布页右侧 `AI智能推荐封面`。
- 抖音 helper 默认使用 `--upload-mode cdp`，不主动改用 `auto`、`dialog` 或 `--current-tab`。
- 快手 helper 必须使用常规视频上传入口；如果页面进入 `VR360°全景视频上传模式`，立即阻断，不得发布。
- 快手必须等视频上传/转码完成后再点击发布；页面仍显示 `上传中`、`预览转码中` 或 `转码过程也可以发布` 时不得发布。
- 报告固定写入 `TEMP/RUN_ID/logs/publish/douyin-publish-report.json`、`kuaishou-publish-report.json` 和 `publish-both-report.json`，并生成对应 `.md`。

## 成功判定

- 抖音和快手都返回 `published`，且聚合报告结论为 `published`，才判定本模块整体发布成功。
- 任一平台失败不回滚另一个平台已发布结果；必须在两个平台都尝试后报告整体状态。
- 发布后无需核对创作者中心内容列表。
- 任一平台 `内容由AI生成` 声明失败、上传未完成、发布按钮无法点击或 helper 无法完成点击时，记录该平台失败；另一个平台仍继续尝试。
