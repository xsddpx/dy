# 模块 00：环境修复与最佳实践

## 职责

- 本模块默认跳过，不是日更启动前置步骤。
- 只有用户明确要求修环境，或流程中遇到环境类问题时才读取并执行。
- 先定位症状，再复用本模块已有最佳实践，执行最小修复，最后用原失败点或最小验证命令确认恢复。
- 每次真实修复后，把可复用经验追加到“环境修复最佳实践记录”，防止后续重复走弯路。

## 环境问题范围

以下问题才进入本模块：

- CDP Chrome 无法启动、端口不可用、用户目录不匹配或 Playwright 无法接管。
- 抖音或快手创作者中心登录态失效、验证码、账号安全验证、平台风控入口阻断。
- Dreamina CLI 登录、积分查询、上传、下载、网络代理或命令依赖异常。
- Python、Playwright、浏览器依赖、文件权限、`TEMP/`、`OUTPUT/`、固定素材读写异常。
- 代理设置异常；本机网络必须保持代理可用，不临时断开代理。

以下问题不属于环境修复：

- TNS/安全拦截；按对应生成模块的 `v1-v5` 收敛规则处理。
- `grid-prompt.txt` 或派生 prompt 不合格。
- 视频审美失败、角色不像、动作不好、画面质量不达标。
- 平台正常审核中、发布后数据表现不佳。

## 修复优先级

1. 记录原始症状：失败命令、报错、平台、当前 `RUN_ID`、是否影响抖音或快手。
2. 对照本模块“环境修复最佳实践记录”，优先复用已有判断和命令。
3. 做最小修复：只处理当前阻断项，不顺手重置无关账号、目录、素材或脚本。
4. 用原失败点复测；原失败点成本过高时，用最小验证命令复测。
5. 如果修复产生可复用经验，追加到本模块记录区。

## 常见修复入口

### CDP Chrome 与 Playwright

- 固定执行账户为 macOS 用户 `xsddpx`。
- 固定 CDP 地址为 `http://127.0.0.1:9222`。
- 固定用户目录为 `/Users/xsddpx/Library/Application Support/Google/Chrome-Codex-CDP`。
- 需要启动或刷新 CDP Chrome 时使用：

```bash
zsh TOOLS/open_cdp_chrome.sh 9222
```

- 需要单独诊断 Playwright 和 CDP 可用性时使用：

```bash
python3 TOOLS/douyin_publish_preflight.py --cdp-url http://127.0.0.1:9222
```

- 发布、抽帧 helper 内部仍会在动作现场检查 CDP/Playwright；这些检查失败时，按本模块修复。

### 抖音与快手登录态

- 登录态失败、验证码、账号安全验证或风控提示属于环境问题。
- 单个平台失败时，先记录该平台失败，再按发布模块规则继续尝试另一个平台；环境修复只处理失败平台的登录态或接管问题。
- 修复后用原发布 helper 的 `--no-publish` 或原失败命令验证，不靠肉眼看到页面打开就判定恢复。

### Dreamina

- CLI 登录、积分、上传、下载、代理或依赖错误属于环境问题。
- Dreamina 明确返回 TNS/安全拦截不属于环境问题。
- 网络异常先检查代理，不临时断开代理。
- 查询结果出现传输类错误时，优先复用同一个 `submit_id` 重查，不先重提生成。

### 文件与依赖

- `MATERIAL/fixed-role/anna.png` 缺失、`TEMP/` 或 `OUTPUT/` 不可读写属于环境问题。
- Python/Playwright 依赖异常时，优先使用当前项目已验证的解释器和依赖路径，不随意升级全局环境。

## 环境修复最佳实践记录

记录格式：

```text
### YYYY-MM-DD 症状标题
- 症状：
- 根因：
- 修复动作：
- 验证：
- 下次判断：
```

记录规则：

- 只记录可复用经验，不写本次无关流水账。
- 不写入 API key、cookie、密码、验证码或账号敏感信息。
- 一次修复只追加一条最小记录；相同根因复发时更新判断规则即可。

### 2026-07-01 抖音上传页 CDP 导航超时
- 症状：`douyin_publish_helper.py` 预检通过，但打开 `https://creator.douyin.com/creator-micro/content/upload` 时 `Page.goto` 在 20 秒 `domcontentloaded` 等待内超时；快手可正常发布。
- 根因：抖音创作者中心上传页偶发加载慢，默认 `--cdp-timeout 20` 不足以完成首轮 Playwright-CDP 导航和文件输入接管。
- 修复动作：只重试抖音单平台，保留原视频、标题、标签和 `--no-location`，将 `--cdp-timeout` 放宽到 `60`。
- 验证：同一条 `RUN_ID` 用抖音单平台重试完成上传、中间帧封面、`内容由AI生成` 自主声明和发布，报告返回 `published`。
- 下次判断：若 CDP/登录态预检均通过且失败点只是上传页 `Page.goto` 超时，优先单平台重试并加 `--cdp-timeout 60`；只跳过同一 `RUN_ID`、同一成片、同一平台已 `published` 的完全相同发布动作，不按日期或条数限制后续发布。

### 2026-07-04 Dreamina 单图相对路径上传失败
- 症状：`dreamina multimodal2video --image MATERIAL/fixed-role/anna.png ...` 返回 `upload phase, no file upload`，未进入生成阶段，不是 TNS。
- 根因：Dreamina CLI 本次对相对路径图片上传没有实际提交文件。
- 修复动作：保持同一个 `vid-prompt-v1.txt` 和单图输入不变，将 `--image` 改为 `/Users/Shared/codex/dy/MATERIAL/fixed-role/anna.png` 绝对路径后重提。
- 验证：绝对路径重提成功返回 `submit_id`，同一任务后续 `query_result` 返回 `success` 并下载 720x1280、约 5 秒 MP4。
- 下次判断：若 Dreamina 在上传阶段报 `no file upload`，先用固定素材绝对路径重试；不要改 prompt、不要进入 TNS 收敛。

### 2026-07-09 发布前 CDP 端口未启动且存在普通 Chrome
- 症状：`publish_adapter.py both` 在抖音和快手预检阶段均失败，`127.0.0.1:9222` connection refused，进程检查发现只有普通 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`，没有固定用户目录的 CDP Chrome。
- 根因：当前账户只开了普通 Chrome，未使用 `/Users/xsddpx/Library/Application Support/Google/Chrome-Codex-CDP` 和 `--remote-debugging-port=9222`。
- 修复动作：运行 `zsh TOOLS/open_cdp_chrome.sh 9222`，脚本关闭错误目录普通 Chrome 并启动固定 CDP Chrome。
- 验证：`python3 TOOLS/douyin_publish_preflight.py --cdp-url http://127.0.0.1:9222` 返回 `ok: true`，进程命令含固定用户目录和 `--remote-debugging-port=9222`。
- 下次判断：若发布预检显示 `connection refused` 且 wrong Chrome 只有普通进程，直接运行固定 CDP 启动脚本，再用 preflight 复测后重试发布。

### 2026-07-10 Dreamina 成功任务下载副本被截断
- 适用边界：本条仅用于文件大小、哈希、播放或解码出现异常迹象的下载排障；默认视频质检按模块 02 使用 `ffprobe` 核对基础规格。
- 症状：`query_result` 已返回 `success`，但同一 `submit_id` 下载出的 MP4 大小和哈希不一致，`ffprobe` 可读到头信息，`ffmpeg -xerror` 全文件解码时报 `partial file` 或 `Invalid NAL unit size`。
- 根因：慢速媒体传输尚未真正结束时又向同一路径发起查询或整理文件，下载副本被截断或覆盖；生成任务本身已经成功，不需要重新提交。
- 修复动作：保留同一 `submit_id`，刷新一次查询结果获得当前临时媒体地址，只向全新目标文件发起一次可重试下载，并等待实际下载进程退出；下载期间不再向同一目标重复调用 `query_result`。
- 验证：目标文件大小停止增长后，先用 `ffmpeg -xerror -v error -i INPUT -f null -` 做全文件严格解码，再核对 `ffprobe` 的分辨率、方向和时长；全部通过后才复制到 `OUTPUT/`。
- 下次判断：Dreamina 返回成功但 MP4 哈希或大小不稳定时，按下载传输异常处理，先复用原任务完整取回并严格解码；不得把可读头信息等同于完整成片，也不得因此重提生成。
