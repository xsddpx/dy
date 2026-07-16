# 环境修复案例库

本案例库保存经过真实修复和验证的可复用经验，配合[环境修复 Runbook](ENVIRONMENT_REPAIR.md)使用；它不是日更流程步骤。

## 记录格式

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

## 已验证案例

### 2026-07-01 抖音上传页 CDP 导航超时

- 症状：`douyin_publish_helper.py` 预检通过，但打开 `https://creator.douyin.com/creator-micro/content/upload` 时 `Page.goto` 在 20 秒 `domcontentloaded` 等待内超时；快手可正常发布。
- 根因：抖音创作者中心上传页偶发加载慢，默认 `--cdp-timeout 20` 不足以完成首轮 Playwright-CDP 导航和文件输入接管。
- 修复动作：只重试抖音单平台，保留原视频、标题、标签和 `--no-location`，将 `--cdp-timeout` 放宽到 `60`。
- 验证：同一条 `RUN_ID` 用抖音单平台重试完成上传、中间帧封面、`内容由AI生成` 自主声明和发布，报告返回 `published`。
- 下次判断：若 CDP/登录态预检均通过且失败点只是上传页 `Page.goto` 超时，优先单平台重试并加 `--cdp-timeout 60`；只跳过同一 `RUN_ID`、同一成片、同一平台已 `published` 的完全相同发布动作，不按日期或条数限制后续发布。

### 2026-07-04 Dreamina 单图相对路径上传失败

- 症状：`dreamina multimodal2video --image MATERIAL/fixed-role/anna.png ...` 返回 `upload phase, no file upload`，未进入生成阶段，不是 TNS。
- 根因：Dreamina CLI 本次对相对路径图片上传没有实际提交文件。
- 修复动作：当时保持同一个 `vid-prompt-v1.txt` 和单图输入不变，从 Git 根目录解析 `MATERIAL/fixed-role/anna.png` 的绝对路径后重提。
- 验证：绝对路径重提成功返回 `submit_id`，同一任务后续 `query_result` 返回 `success` 并下载 MP4。
- 下次判断：若 Dreamina 在上传阶段报 `no file upload`，先把当前模式的全部固定输入图解析为绝对路径，保持图片数量、顺序和 prompt 不变后重试；不要进入 TNS 收敛。

### 2026-07-09 发布前 CDP 端口未启动且存在普通 Chrome

- 症状：`publish_adapter.py both` 在抖音和快手预检阶段均失败，`127.0.0.1:9222` connection refused，进程检查发现只有普通 Chrome，没有带 `--remote-debugging-port=9222` 的 CDP Chrome。
- 根因：普通 Chrome 已启动，但项目 CDP Chrome 尚未启动。
- 修复动作：运行 `zsh TOOLS/open_cdp_chrome.sh 9222` 启动独立 CDP Chrome。
- 验证：`.venv/bin/python TOOLS/douyin_publish_preflight.py --cdp-url http://127.0.0.1:9222` 返回 `ok: true`，进程命令含 CDP 数据目录和 `--remote-debugging-port=9222`。
- 下次判断：若发布预检显示 `connection refused` 且只有普通 Chrome，直接运行 CDP 启动脚本，再用 preflight 复测后重试发布。

### 2026-07-12 迁移后 Python 依赖缺失

- 症状：系统 Python 缺少 OpenCV、NumPy、Playwright 和 pytest，迁移来的 `TEMP/.venv-publish` 含断裂解释器链接。
- 根因：虚拟环境和本机命令不能跨电脑直接迁移，仓库此前没有统一的本地环境重建入口。
- 修复动作：新增并运行 `zsh TOOLS/setup_env.sh --recreate`，将原 `.venv/` 备份到 `TEMP/env-backups/` 后重建。
- 验证：OpenCV、NumPy、Playwright、pytest 可导入，项目全量测试通过。
- 下次判断：迁移或 `.venv/` 失效时直接运行 `zsh TOOLS/setup_env.sh --recreate`；普通依赖补装才使用不带参数的 `zsh TOOLS/setup_env.sh`。

### 2026-07-12 CDP 启动脚本残留旧设备 Profile 名称

- 症状：启动脚本写死读取旧设备的 Profile 名称，与本机普通 Chrome 当前 Profile 不一致，导致 9222 无法启动。
- 根因：脚本把源 Profile 名称当作跨设备固定值。
- 修复动作：启动脚本改为读取普通 Chrome `Local State` 中当前使用的 Profile，缺省使用 `Default`；刷新参数统一为 `--refresh-from-browser`。
- 验证：脚本从 `Default` 初始化 CDP 数据目录，9222 可访问，Playwright 与进程目录预检均通过。
- 下次判断：源 Profile 变化时由脚本自动识别；需要覆盖时使用 `CHROME_PROFILE_DIRECTORY` 环境变量，不在脚本中写死设备历史名称。

### 2026-07-12 普通 Chrome 与 CDP Chrome 互斥

- 症状：CDP 启动脚本会关闭普通 Chrome，导致 ChatGPT Chrome 插件控制通道消失；重新打开普通 Chrome 后，旧预检又将其视为错误进程。
- 根因：旧环境把所有非 CDP Chrome 进程都当作阻断项，与单账户下插件和发布自动化并行使用的需求冲突。
- 修复动作：启动脚本保留普通 Chrome；只有首次初始化或刷新 Profile 时临时关闭并在复制后恢复。预检只要求唯一匹配的 CDP 进程，把普通 Chrome 记录为辅助进程。
- 验证：普通 Chrome 的插件通道与 9222 CDP 同时可用，CDP 进程目录和 Playwright 预检通过。
- 下次判断：普通 Chrome 存在不再构成发布阻断；只有 CDP 目标进程缺失、重复或端口被其他进程占用时进入修复。

### 2026-07-12 CDP 静态预检通过但实际接管报协议错误

- 症状：端口、进程目录和静态预检均正常，但发布 helper 的 `connect_over_cdp` 返回 `Browser.setDownloadBehavior: Browser context management is not supported`。
- 根因：独立 CDP Chrome 旧进程的浏览器协议状态异常，静态端口检查无法覆盖真实 Playwright 接管。
- 修复动作：只结束独立 CDP Chrome 目标进程，再用 `TOOLS/open_cdp_chrome.sh 9222` 重启，保留普通 Chrome。
- 验证：先运行最小 `playwright.chromium.connect_over_cdp` 得到一个浏览器上下文，再重试原发布命令，抖音与快手均返回 `published`。
- 下次判断：遇到相同协议错误时不要只重复静态 preflight；重启独立 CDP 进程并以真实 `connect_over_cdp` 作为恢复判定。
