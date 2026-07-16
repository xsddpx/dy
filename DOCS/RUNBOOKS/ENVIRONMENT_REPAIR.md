# 环境修复 Runbook

## 职责

- 本 runbook 默认跳过，不是日更启动前置步骤。
- 只有用户明确要求修环境，或流程中遇到环境类问题时才读取并执行。
- 先定位症状，再复用[环境修复案例库](ENVIRONMENT_CASES.md)中的已有经验，执行最小修复，最后用原失败点或最小验证命令确认恢复。
- 每次真实修复后，把可复用经验追加到环境修复案例库，防止后续重复走弯路。

## 环境问题范围

以下问题才进入本 runbook：

- CDP Chrome 无法启动、端口不可用、用户目录不匹配或 Playwright 无法接管。
- 抖音或快手创作者中心登录态失效、验证码、账号安全验证、平台风控入口阻断。
- Dreamina CLI 登录、积分查询、上传、下载、网络代理或命令依赖异常。
- Python、Playwright、浏览器依赖、文件权限、`TEMP/`、`OUTPUT/`、固定素材读写异常。
- 代理设置异常；本机网络必须保持代理可用，不临时断开代理。

以下问题不属于环境修复：

- TNS/安全拦截；按[主链阶段 03：视频生成](../PIPELINE/03_VIDEO_GENERATION.md)的 `v1-v5` 收敛规则处理。
- vid prompt 不合格；返回[主链阶段 02：选题与 Prompt](../PIPELINE/02_CONTENT_AND_PROMPT.md)修正。
- 视频审美失败、角色不像、动作不好、画面质量不达标。
- 平台正常审核中、发布后数据表现不佳。

## 修复优先级

1. 记录原始症状：失败命令、报错、平台、当前 `RUN_ID`、是否影响抖音或快手。
2. 对照[环境修复案例库](ENVIRONMENT_CASES.md)，优先复用已有判断和命令。
3. 做最小修复：只处理当前阻断项，不顺手重置无关账号、目录、素材或脚本。
4. 用原失败点复测；原失败点成本过高时，用最小验证命令复测。
5. 如果修复产生可复用经验，按案例库格式追加到 `ENVIRONMENT_CASES.md`。

## 常见修复入口

### CDP Chrome 与 Playwright

- 固定 CDP 地址为 `http://127.0.0.1:9222`。
- 启动脚本从普通 Chrome 当前使用的 Profile 初始化独立 CDP 数据目录；普通 Chrome 与 CDP Chrome 可并存，需要重新同步登录态时使用 `--refresh-from-browser`。
- 自动化默认使用 Playwright `connect_over_cdp` 接管该浏览器；AppleScript 和系统文件选择器仅作为兼容兜底。静态端口预检不能替代真实 CDP 接管验证。
- 需要启动或刷新 CDP Chrome 时使用：

```bash
zsh TOOLS/open_cdp_chrome.sh 9222
```

- 需要单独诊断 Playwright 和 CDP 可用性时使用：

```bash
.venv/bin/python TOOLS/douyin_publish_preflight.py --cdp-url http://127.0.0.1:9222
```

- 发布、抽帧 helper 内部仍会在动作现场检查 CDP/Playwright；这些检查失败时，按本 runbook 修复。

### 抖音与快手登录态

- 登录态失败、验证码、账号安全验证或风控提示属于环境问题。
- 单个平台失败时，先记录该平台失败，再按[主链阶段 05：发布](../PIPELINE/05_PUBLISH.md)的规则继续尝试另一个平台；环境修复只处理失败平台的登录态或接管问题。
- 修复后用原发布 helper 的 `--no-publish` 或原失败命令验证，不靠肉眼看到页面打开就判定恢复。

### Dreamina

- CLI 登录、积分、上传、下载、代理或依赖错误属于环境问题。
- Dreamina 明确返回 TNS/安全拦截不属于环境问题。
- 网络异常先检查代理，不临时断开代理。
- 查询结果出现传输类错误时，优先复用同一个 `submit_id` 重查，不先重提生成。

### 文件与依赖

- `MATERIAL/fixed-role/anna.png` 缺失、找不到任何 `MATERIAL/fixed-environment/anna-room-NN.png` 正式环境图、本次 `environment-path.txt` 指向无效文件，或 `TEMP/`、`OUTPUT/` 不可读写，均属于环境问题。
- Python 依赖统一安装在仓库根目录 `.venv/`；项目命令使用 `.venv/bin/python`。
- Python/Playwright 依赖异常或项目刚从其他电脑迁移时，运行 `zsh TOOLS/setup_env.sh --recreate`；脚本先把原 `.venv/` 备份到 `TEMP/env-backups/`，再重建项目环境。

## 可复用案例

具体症状、根因、修复动作和恢复判定统一维护在[环境修复案例库](ENVIRONMENT_CASES.md)。修复当前问题前先查找相同症状；确认产生新的可复用经验后，再按案例库格式追加记录。
