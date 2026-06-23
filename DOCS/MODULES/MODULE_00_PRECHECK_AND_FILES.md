# 模块 00：预检与文件归档

## 职责

- 确认本次任务是独立新任务。
- 检查 CDP Chrome、Kie API key、Dreamina CLI、抖音创作者中心登录态、文件读写和固定角色素材。
- 创建 `TEMP/RUN_ID/`，初始化运行记录。

## 必查项

- 检查当前账户，默认使用 macOS 账户 `xsddpx` 的运行环境
- 固定执行账户的 CDP Chrome 可用。
- 以固定执行账户环境运行 `TOOLS/douyin_publish_preflight.py --cdp-url http://127.0.0.1:9222` 通过。
- 需要接入 CDP 时优先使用 Playwright `connect_over_cdp`；非 Playwright 链路只用于人工排障或兼容兜底。
- `dreamina user_credit` 可查询账户积分。
- `MATERIAL/fixed-role/anna.png` 存在。
- `TEMP/`、`OUTPUT/` 可读写。

## 固定执行账户

`dy auto` 固定使用 macOS 账户 `xsddpx` 的运行环境，不以当前 Codex 所在账户为准；CDP Chrome 固定为 `http://127.0.0.1:9222`，用户目录应为 `/Users/xsddpx/Library/Application Support/Google/Chrome-Codex-CDP`，Kie API key、Dreamina 与抖音创作者中心登录态也以 `xsddpx` 为准。跨账户执行 Kie 确认图、Dreamina 视频、发布预检或相关自动化命令时必须使用 `sudo -H -u xsddpx ...`，确保 `HOME=/Users/xsddpx`；若 `9222` 已由 `xsddpx` 的 `Chrome-Codex-CDP` 占用且预检通过，直接复用，不关闭、不抢占、不改用当前账户环境。

## 成功接管账户 `xsddpx` CDP CHROME的关键
第一，必须把 Chrome 真正启动在 xsddpx 的图形会话里，不能只是“以 xsddpx 身份发命令”。前面反复失败的核心原因，是启动动作被桌面系统接到了当前活跃用户那里，结果进程、资料目录和登录态都串了。后面改成明确走 gui/501 这个会话后，Chrome 主进程才真正落到 xsddpx。
第二，这次其实是慢启动，不是启动失败。脚本默认等 30 秒就判失败，但我后面继续查进程和端口时发现，Chrome 已经起来了，只是 9222 监听比预期晚。真正确认成功的是这几个信号同时成立：
主进程用户是 xsddpx
参数里带着 --user-data-dir=/Users/xsddpx/.../Chrome-Codex-CDP
127.0.0.1:9222 出现 LISTEN
curl /json/version 和发布预检都返回 ok
一句话概括：关键不是单纯“打开了 Chrome”，而是“在对的用户会话里启动，并等到 CDP 端口真的起来”。

## 命名

- `RUN_ID`：`YYYYMMDD-HHmm-参考代号主题`。
- 过程文件写入 `TEMP/RUN_ID/`。
- 正式成片写入 `OUTPUT/RUN_ID.mp4`。
