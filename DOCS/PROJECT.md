# 项目说明

## 核心目标

本项目是 `anna auto/fast` 日更发布项目，目标是稳定生成并发布单人竖屏短视频。

- 默认路线：`anna` 单人。
- 默认模式：`auto/fast`，其中 `auto` 就是 `fast`。
- 显式模式：`slow`，用于 Kie 确认图流程。
- 视频规格：9:16、720p、5-6 秒。
- 生成工具：Dreamina CLI 负责视频；Kie API 仅在显式 `slow` 模式负责确认图。
- 发布渠道：抖音创作者中心，发布前必须设置 `自主声明 -> 内容由AI生成`。

## 核心卖点与方向

本项目旨在维持高辨识度角色一致性的前提下，稳定输出符合特定审美偏好的抖音短视频。

- 受众定位：成年男性强性吸引偏好用户。
- 视觉卖点：夸张成熟身材、巨大胸部视觉体量、成熟曲线、修身穿搭、清晰腰线、上身辨识度。
- 风格调性：纯欲反差、擦边吸引力、轻熟性感、克制诱惑感、活泼互动感与生活化动作。
- 表情策略：参考优先，表情随动作、镜头距离和场景自然变化；微笑允许存在，但不得作为每条视频的默认模板或固定结尾。
- 合规要求：内部聚焦增长卖点；prompt 只写可见画面、动作和镜头语言，不写合规说明；发布文案必须保持平台可发布表达。严禁生成低俗、裸体及未成年感内容。

## 内容边界

- 只写可见画面、动作、镜头、场景、穿搭和画面质感。
- 严禁低俗、裸体、未成年感和不可发布内容。
- 默认执行 `anna auto/fast` 单图发布链路。
- 只有用户明确指定 `slow`、`慢速模式`、`Kie 确认图`、`确认图流程` 或 `完整确认图流程` 时，才启用中间生图流程。
- 不接入其他生成路线、角色或兜底工具。

## 固定资产

- 固定角色图：`MATERIAL/fixed-role/anna.png`，这是一张同一位成年女性的多视角、多表情角色参考图。
- 参考去重账本：`MATERIAL/reference-history.json`

## 本地环境

- 固定执行账户 `xsddpx` 的 CDP Chrome：`TOOLS/open_cdp_chrome.sh`，默认 `http://127.0.0.1:9222`。
- Chrome 用户数据目录：`/Users/xsddpx/Library/Application Support/Google/Chrome-Codex-CDP`。
- CDP 接入默认优先使用 Playwright `connect_over_cdp`；AppleScript、系统文件选择器等只作为人工排障或兼容兜底。
- auto/fast 视频：`dreamina multimodal2video` 只上传 `MATERIAL/fixed-role/anna.png`，`--model_version seedance2.0_vip --video_resolution 720p --duration 5|6`。
- slow 确认图：`nano-banana-pro`，9:16，1K，PNG；Kie 只上传 `MATERIAL/fixed-role/anna.png` 作为 `@图1`，每次只生成 `A-01` 单张确认图；slow 视频只上传经用户确认的 Kie 原始确认图。
- TNS/安全拦截导致图片或视频未生成时，允许在当前模式、当前生成节点内从 `v1` 收敛到 `v5`；`v1` 是首次提交，`v2-v5` 是最多 4 次逐步收敛。
- TNS 收敛只适用于生成工具明确返回 TNS/安全拦截且没有生成产物的情况；网络、登录、积分、参数错误、上传失败、超时等仍按硬阻断处理。

## 目录边界

- `TEMP/`：过程文件，可清理，不作为默认续跑状态。
- `OUTPUT/`：正式成片，扁平化保存为 `OUTPUT/RUN_ID.mp4`。
- `DOCS/`：流程和规则。
- `TOOLS/`：自动化脚本。
- `MATERIAL/`：固定角色素材和去重账本。

## 默认 auto/fast 流程

1. 预检与建档：读取项目文档，检查 CDP Chrome、Kie API key、Dreamina 视频生成、发布登录态、角色素材、`TEMP/` 和 `OUTPUT/`。
2. 参考选择：没有用户指定参考时，从抖音收藏抽样；进入流程前先做 7 天去重。
3. 参考宫格、类型识别、导演结构反推与 grid-prompt 规范记录：用 `browser_reference_grid.py` 通过 Playwright-CDP 从 CDP Chrome 视频像素抽 6 帧并生成 `reference-grid.jpg`，执行者根据宫格或帧图先完成参考类型识别，再反推可见导演结构、身材卖点校准和参考六锁定结论，并写入 `grid-prompt.txt`；`reference-grid.jpg` 只用于分析与记录，不作为 Dreamina 视频生成输入。
4. 视频提示词：执行者根据 `anna.png` 的角色身份和 `grid-prompt.txt` 的参考类型、可见导演结构人工重写可直接提交 Dreamina 的 `vid prompt`；prompt 使用 `@图1` 指代 `anna.png`，不得含第二张图片引用，不得出现文件名、流程说明或“吸收/根据某文件”的解释性表达。
5. 视频生成：只上传 `MATERIAL/fixed-role/anna.png` 作为 `@图1` 后提交 Dreamina 视频。
6. 发布：下载正式 MP4 到 `OUTPUT/RUN_ID.mp4`，上传抖音并设置 `内容由AI生成` 声明。
7. 记录收尾：成功生成正式视频后写入去重账本；发布后只在运行记录中补充发布状态并刷新记录。

## 显式 slow 模式

- `slow` 只有用户明确说 `slow`、`慢速模式`、`Kie 确认图`、`确认图流程` 或 `完整确认图流程` 时才启用。
- `slow` 在模块 01 后执行模块 02：执行者直接查看 `reference-grid.jpg` 或帧图，重点分析穿搭、环境、人物姿态和镜头关系，结合 `anna.png` 的角色身份规则，人工重写 Kie 可直接执行的五段式 `img prompt`；`grid-prompt.txt` 不作为 slow 确认图 img prompt 的来源；Kie Nano Banana Pro 1K 只上传 `anna.png` 作为 `@图1`，每批固定生成 `A-01` 单张确认图。
- `slow` 必须在 A-01 确认图生成后硬停，展示确认图、输入来源、img prompt、TNS 收敛记录和是否建议使用；等待用户明确确认后，才能记录 `selected_slot=A-01`、`selected_confirmation_image` 和选择原因，并进入视频生成。
- `slow` 视频生成综合 `img prompt` 和 `grid-prompt.txt` 的参考类型、可见导演结构重新写成可直接提交 Dreamina 的最终 `vid prompt`，只上传选中确认图作为 `@图1` 后提交 Dreamina 视频。
- 不因 `auto/fast` 失败自动切换到 `slow`，也不因 `slow` 失败自动切回 `auto/fast`。
- slow 确认图若因 TNS/安全拦截未生成图片，只对 `A-01` 按 `v2-v5` 继续收敛；到 `v5` 仍未生成则停止，不生成第二张、不切换模式、不接入其他路线或兜底工具。

## 硬阻断

- 参考宫格未通过，不进入提示词或生成。
- `auto/fast` 缺少 `MATERIAL/fixed-role/anna.png`、`reference-grid-report.json` 通过记录、含参考类型识别的 `grid-prompt.txt` 时，不进入视频生成。
- `slow` 没有可用确认图或未记录选中确认图，不进入视频生成。
- 视频生成只允许上传 `@图1` 单图；vid prompt 含第二张图片引用或 Dreamina 命令包含第二个 `--image` 时，不进入提交。
- 视频或图片生成因 TNS/安全拦截到 `v5` 仍未产出时停止，不发布，不切换 `fast/slow`，并报告 `v1-v5` 失败摘要。
- 发布前未完成 `内容由AI生成` 声明，不得发布。
- 登录失效、验证码、账号安全、平台风控、上传失败、发布按钮禁用等平台阻断时停止并报告。
