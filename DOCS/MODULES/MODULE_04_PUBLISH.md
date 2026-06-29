# 模块 04：双平台发布

## 职责

- 将 `OUTPUT/RUN_ID.mp4` 同步上传到抖音和快手。
- 两个平台都设置 `自主声明/作品声明 -> 内容由AI生成`。
- 填写标题、简介和标签。
- 抖音按当天行程大方向尽量添加发布位置；快手不设置发布地址。
- 点击两个平台发布按钮并记录抖音、快手和整体结果。

## 前置条件

- 已完成模块 03，正式成片已保存为 `OUTPUT/RUN_ID.mp4`。
- 已满足模块 03 的确认规则：fast 默认可直接发布；fast 显式确认任务或 slow 已取得用户发布确认。
- 已完成模块 00 发布预检，固定执行账户 `xsddpx` 的 CDP Chrome、抖音创作者中心登录态和快手创作者中心登录态可用。
- 本模块只发布本次 `RUN_ID` 的正式成片，不因 `TEMP/` 或 `OUTPUT/` 中存在旧文件而发布旧任务。

## 执行入口

模块 04 默认使用 `TOOLS/publish_adapter.py both` 依次编排抖音和快手发布。固定顺序为先抖音、后快手；抖音失败也必须继续尝试快手。

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
  --location "上海 武康路与安福路街区" \
  --cdp-url http://127.0.0.1:9222 \
  --out-dir TEMP/RUN_ID/logs/publish \
  --record-jsonl TEMP/RUN_ID/RUN_ID-run-record.jsonl
```

要求：

- `--title` 必填；标签使用 tag 池随机抽取 4 个。
- 默认自动读取 `MATERIAL/anna-weekly-itinerary.json` 的当天 `city` 和 `location`，作为抖音位置查询词；如果本次内容大方向更具体，可显式传入 `--location "城市 大概地点"` 覆盖。
- 抖音 helper 可拆分复合位置词重试；只选择同时匹配具体地点和城市上下文的 POI，避免误选同名外地位置。
- 抖音位置只需按当天行程大方向选择差不多匹配的 POI；页面未显示位置控件、搜索无结果或控件被平台动态替换时，记录 warning 后继续，不作为发布硬阻断。
- 快手 helper 为兼容双平台入口会接受 `--location` / `--no-location` / `--location-timeout`，但固定跳过地址设置，不产生位置 warning。
- 抖音 helper 默认使用 `--upload-mode cdp`，不主动改用 `auto`、`dialog` 或 `--current-tab`。
- 快手 helper 必须使用常规视频上传入口；如果页面进入 `VR360°全景视频上传模式`，立即阻断，不得发布。
- 快手必须等视频上传/转码完成后再点击发布；页面仍显示 `上传中`、`预览转码中` 或 `转码过程也可以发布` 时不得发布。
- 报告固定写入 `TEMP/RUN_ID/logs/publish/douyin-publish-report.json`、`kuaishou-publish-report.json` 和 `publish-both-report.json`，并生成对应 `.md`。

## 成功判定

- 抖音和快手都返回 `published`，且聚合报告结论为 `published`，才判定本模块整体发布成功。
- 任一平台失败不回滚另一个平台已发布结果；必须在两个平台都尝试后报告整体状态。
- 发布后无需核对创作者中心内容列表。
- 任一平台 `内容由AI生成` 声明失败、上传未完成、发布按钮无法点击或 helper 无法完成点击时，记录该平台失败；另一个平台仍继续尝试。
