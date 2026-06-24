# dy

`/Users/Shared/codex/dy` 是 `anna auto/fast` 抖音日更项目，默认执行单图视频生成发布链路。

## 固定流程

1. 从用户指定参考或抖音收藏选参考。
2. 7 天去重。
3. 通过 Playwright-CDP 从 CDP Chrome 抽帧生成参考宫格，并根据宫格写 `grid-prompt.txt`。
4. 根据 `grid-prompt.txt` 人工重写 `vid-prompt.txt`。
5. Dreamina `multimodal2video` 只上传 `MATERIAL/fixed-role/anna.png` 生成 5-6 秒竖屏视频。
6. 下载并质检 MP4。
7. 上传抖音，设置 `内容由AI生成` 声明并发布。
8. 记录产物、去重账本和发布状态。

## 边界

只执行 `anna auto/fast` 模式。
显式 `slow` 模式用于中间生图流程，不接入其他生成路线、角色或兜底工具。

CDP 接入默认优先使用 Playwright `connect_over_cdp`；AppleScript、系统文件选择器等只作为人工排障或兼容兜底。

## 入口

```bash
cd /Users/Shared/codex/dy
zsh TOOLS/open_cdp_chrome.sh 9222
python3 TOOLS/douyin_publish_preflight.py --cdp-url http://127.0.0.1:9222
```

只有执行显式 `slow` 模式时才需要 Kie 确认图；生图前先在本地 `.env` 配置 `KIE_API_KEY`，不要提交 `.env`。
