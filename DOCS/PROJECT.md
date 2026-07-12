# 项目说明

## 核心目标

本项目固定执行 `anna auto/fast` 双图参考日更链路，其中 `auto` 即 `fast`；稳定生成 9:16、720p、5–7 秒的 Anna 单人竖屏短视频，自动上传到 Google Drive 的 My Drive 根目录，并同步发布到抖音和快手。`@图1` 固定锚定 Anna，`@图2` 固定锚定环境；视频由 Dreamina CLI 生成，两个平台发布前都必须设置 `自主声明/作品声明 -> 内容由AI生成`。

## 核心卖点

本模块由用户本人进行修改。

- 视觉：成熟身材、S 型曲线、上身视觉体量、修身穿搭、清晰腰线和上身辨识度。
- 调性：纯欲反差、轻熟性感、克制诱惑感、成熟女性妩媚感、活泼互动、可见才艺与生活化动作。

## 流程路由

- 默认日更：`DOCS/MODULES/MODULE_01_REFERENCE.md` 自主选题、衣柜匹配与七段式 prompt -> `DOCS/MODULES/MODULE_02_DREAMINA_VIDEO.md` 生成、质检与 Google Drive 上传 -> `DOCS/MODULES/MODULE_03_PUBLISH.md` 双平台发布 -> `DOCS/MODULES/MODULE_04_RECORDS.md` 记录收尾。
- 只生成视频：`DOCS/MODULES/MODULE_01_REFERENCE.md` 自主选题、衣柜匹配与七段式 prompt -> `DOCS/MODULES/MODULE_02_DREAMINA_VIDEO.md` 按 `xdysp` 分支生成、不质检并上传 Google Drive -> `DOCS/MODULES/MODULE_04_RECORDS.md` 记录收尾；不进入模块 03。
- 环境修复：`DOCS/MODULES/MODULE_00_ENV_REPAIR.md`；默认跳过，仅在出现环境问题或用户明确要求时执行。
- 评论任务：`DOCS/MODULES/MODULE_06_COMMENT_REPLY.md`；仅在用户明确要求查看或回复评论时执行。

具体执行细则只看对应模块。

## 创作方向

- 面向偏好成熟性感的成年受众，以 Anna 的修身穿搭、S 型曲线、上身辨识度和清晰腰线为核心视觉。
- 调性保持轻熟、妩媚、活泼且克制，通过穿搭展示和可见才艺形成吸引；模板选择和可见卖点看模块 01。

## 创作总则

- prompt 是核心创作产物；人物表现和穿搭与模块 01 的固定环境图和靠墙动作套装组合，人物与墙面保持真实接触并形成轻微自然投影。
- 全程固定拍摄，拍摄设备位于画外；prompt 只写可见画面、主要动作、人物状态和画面结果。
- Anna 保持明确成年形象、完整穿着、克制表达和平台可发布状态；七段结构与具体写法统一看模块 01。

## 固定资产与目录

- 固定角色图：`MATERIAL/fixed-role/anna.png`，用于锚定同一位成年女性的脸部身份、上身体量、胸部体量比例、纤细腰线、腰胯比例和整体 S 型曲线。
- 固定环境图集合：正式环境图统一存放在 `MATERIAL/fixed-environment/`，文件名使用 `anna-room-NN.png`；每次运行从全部正式编号图中随机选择一张，并将绝对路径锁定到 `TEMP/RUN_ID/environment-path.txt`。环境图 01 为 `anna-room-01.png`：适配膝盖以上中景的 9:16 纯墙面纵图，墙面为干净白墙，左上方固定一幅木色窄框米色抽象画，中央约 60% 作为干净的贴墙动作与投影区。替换前版本、历史版本和 `candidates/` 均不进入随机池。
- Anna 衣柜：`MATERIAL/anna-wardrobe.md`。默认按当天日期优先选择对应编号；当天对应编号不存在时，从现有衣柜条目中随机选择；与卖点或动作模板不适配时可改选，并记录原因。
- `TEMP/` 保存可清理的过程文件，不作为下次默认续跑状态；正式运行目录固定为 `TEMP/RUN_ID/`，正式成片固定为 `OUTPUT/RUN_ID.mp4`，两者使用完全相同的 `RUN_ID`；`DOCS/`、`TOOLS/`、`MATERIAL/` 分别保存规则、自动化脚本和固定资产。

## 运行建档

- 每次执行通过 `TOOLS/run_workspace.py init` 创建唯一 `RUN_ID`。唯一合法格式为 `YYYYMMDD-HHMMSS`；同一秒内首个运行使用纯时间，后续依次使用两位数字后缀 `-01` 至 `-99`，不在 RUN_ID 中加入主题、模式、来源或模板等语义后缀。
- `init` 按 `Asia/Shanghai` 时间原子创建 `TEMP/RUN_ID/logs/` 和 `OUTPUT/`，并向 `TEMP/RUN_ID/RUN_ID-run-record.jsonl` 写入 `run/started` 首条事件；触发来源、scheduled run 或 thread 标识通过事件数据记录。
- 后续所有 prompt、下载、代理图、发布报告和运行记录都使用本次 `RUN_ID`，不从旧目录推断本次状态。
- `TOOLS/run_workspace.py audit` 用于检查正式运行目录、运行记录和 `OUTPUT/*.mp4` 的命名与对应关系；候选、调试、缓存和 `TEMP/del/` 等辅助目录不作为正式 RUN_ID。

## 本地环境

- 所有项目命令先切换到当前 Git 仓库根目录；需要绝对路径时从 `git rev-parse --show-toplevel` 解析，不写死 macOS 用户名。
- CDP Chrome 由 `TOOLS/open_cdp_chrome.sh` 启动，默认地址为 `http://127.0.0.1:9222`；脚本从普通 Chrome 当前使用的 Profile 初始化独立 CDP 数据目录，普通 Chrome 可与 CDP Chrome 并存。
- CDP 默认使用 Playwright `connect_over_cdp`；AppleScript 和系统文件选择器仅作兼容兜底。
- Python 依赖使用项目根目录 `.venv/`。
- Dreamina 固定依次上传 `MATERIAL/fixed-role/anna.png` 和本次 `TEMP/RUN_ID/environment-path.txt` 锁定的随机环境图，分别对应 `@图1` 和 `@图2`；参数为 `--model_version seedance2.0_vip --video_resolution 720p --duration 5|6|7`。

## 发布数量与重复阻断

- 项目不设自然日、轮次或条数上限；06:00、18:00、手动 `/xdy`、补跑和新 `RUN_ID` 均独立执行。
- 仅当 scheduled run/thread、`RUN_ID`、成片和平台均相同，且该平台已返回 `published` 时，才跳过重复点击；其他平台、新主题、新成片和补跑继续执行。

## 全局硬阻断

- 生成前必须具备固定角色图和至少一张 `anna-room-NN.png` 正式环境图，并在本次运行中锁定一张环境图；七段式 prompt 必须通过 `@图1` 人物、`@图2` 环境、视频约束与构图校验并包含人物动作段；人物动作正文不做逐字校验；prompt 与 Dreamina 命令必须保持同一组双图输入和固定顺序。
- Dreamina 明确返回 TNS/安全拦截时最多收敛到 `v5`；仍无产物则停止。网络、登录、积分、参数、上传、下载或超时等环境问题转模块 00 修复并复测。
- 发布前必须人工对照固定角色代理图与首中尾三帧。仅胸部体量明显偏小时阻断，其余全部通过。
- 任一平台发布前必须设置 `内容由AI生成`。单个平台受登录、验证、风控、上传或按钮状态阻断时记录失败，并继续尝试另一个平台。
- `xdy` 或 `xdysp` 只要成功整理出 `OUTPUT/RUN_ID.mp4`，都必须尝试上传到 Google Drive 的 My Drive 根目录；上传失败时记录失败原因和补传状态。`xdy` 继续双平台发布，`xdysp` 继续记录收尾，不把云端归档失败作为后续流程阻断项。
