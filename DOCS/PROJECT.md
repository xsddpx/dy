# 项目说明

## 核心目标

本项目固定执行 `anna auto/fast` 单图日更链路，其中 `auto` 即 `fast`；稳定生成 9:16、720p、5–7 秒的 Anna 单人竖屏短视频，并同步发布到抖音和快手。视频由 Dreamina CLI 生成；两个平台发布前都必须设置 `自主声明/作品声明 -> 内容由AI生成`。

## 流程路由

- 默认日更：`DOCS/MODULES/MODULE_01_REFERENCE.md` 自主选题、衣柜匹配与七段式 prompt -> `DOCS/MODULES/MODULE_02_DREAMINA_VIDEO.md` 生成与质检 -> `DOCS/MODULES/MODULE_03_PUBLISH.md` 双平台发布 -> `DOCS/MODULES/MODULE_04_RECORDS.md` 记录收尾。
- 环境修复：`DOCS/MODULES/MODULE_00_ENV_REPAIR.md`；默认跳过，仅在出现环境问题或用户明确要求时执行。
- 评论任务：`DOCS/MODULES/MODULE_06_COMMENT_REPLY.md`；仅在用户明确要求查看或回复评论时执行。

具体执行细则只看对应模块。

## 创作方向

- 面向偏好成熟性感的成年受众，以 Anna 的修身穿搭、S 型曲线、上身辨识度和清晰腰线为核心视觉。
- 调性保持轻熟、妩媚、活泼且克制，通过穿搭展示和可见才艺形成吸引；模板选择和可见卖点看模块 01。

## 创作总则

- prompt 是核心创作产物；人物表现和穿搭与模块 01 的固定环境、动画套装组合。
- 全程固定拍摄，拍摄设备位于画外；prompt 只写可见画面、主要动作、人物状态和画面结果。
- Anna 保持明确成年形象、完整穿着、克制表达和平台可发布状态；七段结构与具体写法统一看模块 01。

## 固定资产与目录

- 固定角色图：`MATERIAL/fixed-role/anna.png`，用于锚定同一位成年女性的脸部身份、上身体量、胸部体量比例、纤细腰线、腰胯比例和整体 S 型曲线。
- Anna 衣柜：`MATERIAL/anna-wardrobe.md`。默认按当天日期优先选择对应编号；与卖点或动画模板不适配时可改选，并记录原因。
- `TEMP/` 保存可清理的过程文件，不作为下次默认续跑状态；`OUTPUT/RUN_ID.mp4` 保存正式成片；`DOCS/`、`TOOLS/`、`MATERIAL/` 分别保存规则、自动化脚本和固定资产。

## 本地环境

- 固定执行账户为 `xsddpx`；CDP Chrome 由 `TOOLS/open_cdp_chrome.sh` 启动，默认地址为 `http://127.0.0.1:9222`，用户目录为 `/Users/xsddpx/Library/Application Support/Google/Chrome-Codex-CDP`。
- CDP 默认使用 Playwright `connect_over_cdp`；AppleScript 和系统文件选择器仅作兼容兜底。
- Dreamina 固定只上传 `MATERIAL/fixed-role/anna.png`，参数为 `--model_version seedance2.0_vip --video_resolution 720p --duration 5|6|7`。

## 发布数量与重复阻断

- 项目不设自然日、轮次或条数上限；06:00、18:00、手动 `/dy`、补跑和新 `RUN_ID` 均独立执行。
- 仅当 scheduled run/thread、`RUN_ID`、成片和平台均相同，且该平台已返回 `published` 时，才跳过重复点击；其他平台、新主题、新成片和补跑继续执行。

## 全局硬阻断

- 生成前必须具备固定角色图，七段式 prompt 必须通过固定环境、动画与视频类型映射校验；prompt 与 Dreamina 命令保持同一个 `@图1` 单图输入。
- Dreamina 明确返回 TNS/安全拦截时最多收敛到 `v5`；仍无产物则停止。网络、登录、积分、参数、上传、下载或超时等环境问题转模块 00 修复并复测。
- 发布前必须人工对照固定角色代理图与首中尾三帧。仅人脸身份明显不一致，或胸部大小、上身体量、腰线、腰胯比例和整体 S 型身材明显不一致或漂移时阻断；其他画面差异记为 warning。
- 任一平台发布前必须设置 `内容由AI生成`。单个平台受登录、验证、风控、上传或按钮状态阻断时记录失败，并继续尝试另一个平台。
