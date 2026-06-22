# dy

`/Users/Shared/codex/dy` 是 `anna auto` 抖音日更项目，只保留完整发布链路。

## 固定流程

1. 从用户指定参考或抖音收藏选参考。
2. 7 天去重。
3. 通过 Playwright-CDP 从 CDP Chrome 抽帧生成参考宫格。
4. 写可见画面 prompt。
5. Dreamina `image2image` 生成三张确认图。
6. 人脸一致性门禁自动选图。
7. Dreamina `multimodal2video` 生成 5-6 秒竖屏视频。
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
