# 模块 00：预检与文件归档

## 职责

- 确认本次任务是独立新任务。
- 对 fast 和 slow 执行同一套完整环境检查。
- 创建 `TEMP/RUN_ID/`，初始化运行记录。

## 必查项

- 检查当前账户，必须只能使用 macOS 账户 `xsddpx` 的运行环境
- 固定执行账户的 CDP Chrome 可用。
- 以固定执行账户环境运行 `TOOLS/douyin_publish_preflight.py --cdp-url http://127.0.0.1:9222` 通过。
- 抖音创作者中心登录态可用。
- 快手创作者中心登录态可用。
- 需要接入 CDP 时优先使用 Playwright `connect_over_cdp`；非 Playwright 链路只用于人工排障或兼容兜底。
- `dreamina user_credit` 可查询账户积分。
- Kie API key 可用。
- `MATERIAL/fixed-role/anna.png` 存在。
- `TEMP/`、`OUTPUT/` 可读写。

## 固定执行账户

所有模式固定使用 macOS 账户 `xsddpx` 的运行环境，不以当前 Codex 所在账户为准。CDP Chrome 固定为 `http://127.0.0.1:9222`，用户目录为 `/Users/xsddpx/Library/Application Support/Google/Chrome-Codex-CDP`。跨账户运行相关命令时使用 `sudo -H -u xsddpx ...`，确保 `HOME=/Users/xsddpx`；已通过预检的 9222 实例直接复用，不关闭或抢占。

## CDP 接管判定

- Chrome 主进程属于 `xsddpx`。
- 启动参数包含固定用户目录。
- `127.0.0.1:9222` 已监听，`/json/version` 和发布预检均返回成功，可同时接管抖音和快手创作者中心。
- 启动较慢时等待端口就绪，不因短时无监听改用其他账户环境。

## 命名

- `RUN_ID`：`YYYYMMDD-HHmm-参考代号主题`。
- 过程文件写入 `TEMP/RUN_ID/`。
- 正式成片写入 `OUTPUT/RUN_ID.mp4`。
