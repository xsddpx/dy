# dy

`/Users/Shared/codex/dy` 是 `anna auto/fast` 抖音日更项目，默认执行单图视频生成发布链路。

## 固定流程

1. 读取当前 active 的 `MATERIAL/anna-weekly-itinerary.json`；只有资产不可用、未开始或当天日期超过 `valid_to` 时，才生成今天起连续 7 天国内真实城市行程并保存为 active。
2. 按当天行程大方向选择参考，优先级和延展场景规则见 `DOCS/PROJECT.md`。
3. 7 天去重。
4. 通过 Playwright-CDP 从 CDP Chrome 抽帧生成参考宫格，再根据宫格写十段式 `grid-prompt.txt`。
5. `grid-prompt.txt` 直接作为 fast 的 Dreamina v1 最终 vid prompt；slow 视频只删除人物段中的 anna 多视角角色卡声明。
6. Dreamina `multimodal2video` 只上传 `MATERIAL/fixed-role/anna.png` 生成 5-6 秒竖屏视频。
7. 下载并质检 MP4。
8. 上传抖音，设置 `内容由AI生成` 声明并发布。
9. 记录产物、去重账本和发布状态。

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

只有执行显式 `slow` 模式时才需要 Kie 确认图；确认图 img prompt 由模块 01 的十段式 `grid-prompt.txt` 删除 `整体动画：` 和 `背景音乐：` 两段得到；Kie 只上传 `MATERIAL/fixed-role/anna.png` 作为角色卡输入，每次只生成 `A-01` 一张确认图。slow 视频阶段改为上传确认图，vid prompt 只从 `grid-prompt.txt` 删除人物段中的 anna 多视角角色卡声明。生图前先在本地 `.env` 配置 `KIE_API_KEY`，不要提交 `.env`。
