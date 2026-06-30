# dy

`/Users/Shared/codex/dy` 是 anna slow 双平台日更项目。流程先生成并确认 Kie 图片，再生成 Dreamina 视频，获得发布确认后同步发布到抖音和快手。

## 固定流程

1. 创建本次 `TEMP/RUN_ID/` 和运行记录；默认跳过模块 00。
2. 读取当前 active 的 `MATERIAL/anna-weekly-itinerary.json`；只有资产不可用、未开始或当天日期超过 `valid_to` 时，才生成今天起连续 7 天国内真实城市行程并保存为 active。
3. 按当天行程大方向选择参考，优先级和延展场景规则见 `DOCS/PROJECT.md`。
4. 检查永久禁用账本；未命中后通过 Playwright-CDP 从 CDP Chrome 抽帧生成参考宫格，再根据宫格写十段式 `grid-prompt.txt`。
5. 派生 Kie 图片 prompt，生成单张确认图并等待用户选图。
6. 用户确认图片后，派生 Dreamina 视频 prompt，只上传选中的 Kie 原始图生成 5-6 秒竖屏视频。
7. 下载并质检 MP4，展示视频并等待用户确认发布。
8. 获得确认后同步上传抖音和快手，两个平台都设置 `内容由AI生成` 声明并发布。
9. 记录产物、确认状态、抖音/快手发布状态和双平台整体状态。

## 边界

只执行 anna slow 模式，不接入其他生成路线、角色或兜底工具。

CDP 接入默认优先使用 Playwright `connect_over_cdp`；AppleScript、系统文件选择器等只作为人工排障或兼容兜底。

模块 00 是环境修复模块，默认跳过；只有遇到 CDP、Playwright、登录态、API key、积分、权限、素材、读写、网络代理等环境问题，或用户明确要求修环境时才读取 `DOCS/MODULES/MODULE_00_ENV_REPAIR.md`。每次真实修复后，把可复用经验追加到模块内的最佳实践记录。

## 入口

```bash
cd /Users/Shared/codex/dy
```

所有日更任务都需要 Kie 确认图；prompt 派生统一使用 `TOOLS/prompt_lint.py derive`，细节见模块 02/03。生图前先在本地 `.env` 配置 `KIE_API_KEY`，不要提交 `.env`。遇到环境问题时再按模块 00 修复。
