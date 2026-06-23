# dy

`/Users/Shared/codex/dy` 是 `anna auto` 抖音日更项目，只保留完整发布链路。

## 固定流程

1. 从用户指定参考或抖音收藏选参考。
2. 7 天去重。
3. 通过 Playwright-CDP 从 CDP Chrome 抽帧生成参考宫格，并根据宫格写 `grid-prompt.txt`。
4. 写确认图 img prompt。
5. Kie Nano Banana Pro 1K 生成两张确认图。
6. 生成人脸相似度参考报告，并由执行者选择确认图。
7. 综合 img prompt 和 grid prompt 人工重写 vid prompt，Dreamina `multimodal2video` 生成 5-6 秒竖屏视频。
8. 上传抖音，设置 `内容由AI生成` 声明并发布。
9. 记录产物、去重账本和发布状态。

## 边界

只执行 `anna auto` 完整发布链路，不接入其他生成路线、角色或兜底工具。

CDP 接入默认优先使用 Playwright `connect_over_cdp`；AppleScript、系统文件选择器等只作为人工排障或兼容兜底。

## 入口

```bash
cd /Users/Shared/codex/dy
zsh TOOLS/open_cdp_chrome.sh 9222
python3 TOOLS/douyin_publish_preflight.py --cdp-url http://127.0.0.1:9222
```

Kie 确认图生图前，先在本地 `.env` 配置 `KIE_API_KEY`，不要提交 `.env`。
