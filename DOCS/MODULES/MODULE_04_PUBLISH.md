# 模块 04：抖音发布

## 职责

- 上传 `OUTPUT/RUN_ID.mp4`。
- 设置 `自主声明 -> 内容由AI生成`。
- 填写标题、简介和标签。
- 按当天行程大方向尽量添加发布位置。
- 点击发布按钮并记录结果。

## 前置条件

- 已完成模块 03，正式成片已保存为 `OUTPUT/RUN_ID.mp4`。
- 已完成模块 00 发布预检，固定执行账户 `xsddpx` 的 CDP Chrome 和抖音创作者中心登录态可用。
- 本模块只发布本次 `RUN_ID` 的正式成片，不因 `TEMP/` 或 `OUTPUT/` 中存在旧文件而发布旧任务。

## 执行入口

模块 04 默认使用 `TOOLS/douyin_publish_helper.py` 执行上传、文案填写、AI 生成声明、发布点击和报告记录。

发布标签从 `MATERIAL/publish-tag-pool.json` 随机抽取，不写 `AI生成`、`AIGC` 或 `内容由AI生成`：

```bash
python3 TOOLS/publish_tag_pool.py --count 4 --shell-args
```

跨账户执行时必须使用固定账户环境：

```bash
sudo -H -u xsddpx python3 TOOLS/douyin_publish_helper.py OUTPUT/RUN_ID.mp4 \
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

- `--title` 必填；标签使用 tag 池随机抽取结果，建议 4-5 个。
- 默认自动读取 `MATERIAL/anna-weekly-itinerary.json` 的当天 `city` 和 `location`，作为发布位置查询词；如果本次内容大方向更具体，可显式传入 `--location "城市 大概地点"` 覆盖。
- helper 会把复合位置拆成多个查询词重试，例如 `上海 武康路与安福路街区` 会依次尝试完整词、去掉城市后的地点词、`上海 武康路`、`上海 安福路`、`武康路`、`安福路街区`、`安福路` 等，优先选择命中具体街区或道路名的 POI。
- 查询词含城市时，helper 会先尝试点击位置控件里的同名城市 tab，再搜索具体地点；只允许点击具体候选项，不点击候选外层容器。候选必须同时命中具体地点和城市/本地上下文，例如 `月光码头步行街 江苏省苏州市...`，避免把含有同名词的外地或海外 POI 误选为发布位置。
- 位置只需按当天行程大方向选择差不多匹配的 POI；页面未显示位置控件、搜索无结果或控件被平台动态替换时，记录 warning 后继续，不作为发布硬阻断。
- 默认使用 `--upload-mode cdp`，不主动改用 `auto`、`dialog` 或 `--current-tab`。
- 报告固定写入 `TEMP/RUN_ID/logs/publish/douyin-publish-report.json` 和 `.md`。

## 成功判定

- 点击发布按钮成功即判定本模块发布成功。
- 发布后无需核对创作者中心内容列表。
- 除 `内容由AI生成` 声明失败、发布按钮无法点击或 helper 无法完成点击外，本模块不设置其他阻断。
