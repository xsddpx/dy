# 模块 00：预检与文件归档

## 职责

- 确认本次任务是独立新任务。
- 检查 CDP Chrome、Kie API key、Dreamina CLI、抖音创作者中心登录态、文件读写和固定角色素材。
- 创建 `TEMP/RUN_ID/`，初始化运行记录。

## 必查项

- 固定执行账户的 CDP Chrome 可用。
- 以固定执行账户环境运行 `TOOLS/douyin_publish_preflight.py --cdp-url http://127.0.0.1:9222` 通过。
- 需要接入 CDP 时优先使用 Playwright `connect_over_cdp`；非 Playwright 链路只用于人工排障或兼容兜底。
- `dreamina user_credit` 可查询账户积分。
- `MATERIAL/fixed-role/anna.png` 存在。
- `MATERIAL/fixed-role/anna-upload-2k.jpg` 是 2048x2048 JPG。
- `TEMP/`、`OUTPUT/` 可读写。

## 固定执行账户

`dy auto` 固定使用 macOS 账户 `xsddpx` 的运行环境，不以当前 Codex 所在账户为准；CDP Chrome 固定为 `http://127.0.0.1:9222`，用户目录应为 `/Users/xsddpx/Library/Application Support/Google/Chrome-Codex-CDP`，Kie API key、Dreamina 与抖音创作者中心登录态也以 `xsddpx` 为准。跨账户执行 Kie 确认图、Dreamina 视频、发布预检或相关自动化命令时必须使用 `sudo -H -u xsddpx ...`，确保 `HOME=/Users/xsddpx`；若 `9222` 已由 `xsddpx` 的 `Chrome-Codex-CDP` 占用且预检通过，直接复用，不关闭、不抢占、不改用当前账户环境。

## 命名

- `RUN_ID`：`YYYYMMDD-HHmm-参考代号主题`。
- 过程文件写入 `TEMP/RUN_ID/`。
- 正式成片写入 `OUTPUT/RUN_ID.mp4`。
