# 项目说明

## 核心目标

本项目是 `anna auto` 日更发布项目，目标是稳定生成并发布单人竖屏短视频。

- 默认路线：`anna` 单人。
- 固定通道：`auto`。
- 视频规格：9:16、720p、5-6 秒。
- 生成工具：Kie API 负责确认图，Dreamina CLI 负责视频。
- 发布渠道：抖音创作者中心，发布前必须设置 `自主声明 -> 内容由AI生成`。

## 核心卖点与方向

本项目旨在维持高辨识度角色一致性的前提下，稳定输出符合特定审美偏好的抖音短视频。

- 受众定位：成年男性强性吸引偏好用户。
- 视觉卖点：夸张成熟身材、巨大胸部视觉体量、成熟曲线、修身穿搭、清晰腰线、上身辨识度。
- 风格调性：纯欲反差、擦边吸引力、轻熟性感、克制诱惑感、活泼互动感与生活化动作。
- 合规要求：内部聚焦增长卖点；prompt 只写可见画面、动作和镜头语言，不写合规说明；发布文案必须保持平台可发布表达。严禁生成低俗、裸体及未成年感内容。

## 内容边界

- 只写可见画面、动作、镜头、场景、穿搭和画面质感。
- 保持成熟、写实、生活化、平台可发布表达。
- 严禁低俗、裸体、未成年感和不可发布内容。
- 默认执行 `anna auto` 完整发布链路；只有用户明确指定“快速通道”“跳过确认图”或“备用流程”时，才启用快速通道备选。
- 不接入其他生成路线、角色或兜底工具。

## 固定资产

- 固定角色图：`MATERIAL/fixed-role/anna.png`，这是一张同一位成年女性的多视角、多表情角色参考图。
- 参考去重账本：`MATERIAL/reference-history.json`

## 本地环境

- 固定执行账户 `xsddpx` 的 CDP Chrome：`TOOLS/open_cdp_chrome.sh`，默认 `http://127.0.0.1:9222`。
- Chrome 用户数据目录：`/Users/xsddpx/Library/Application Support/Google/Chrome-Codex-CDP`。
- CDP 接入默认优先使用 Playwright `connect_over_cdp`；AppleScript、系统文件选择器等只作为人工排障或兼容兜底。
- Kie 确认图：`nano-banana-pro`，9:16，1K，PNG。
- Dreamina 视频主流程：`dreamina multimodal2video` 同时上传选中确认图和参考宫格图，`--model_version seedance2.0_vip --video_resolution 720p --duration 5|6`。
- Dreamina 视频快速通道：仅在用户显式指定时，直接上传 `MATERIAL/fixed-role/anna.png` 和 `TEMP/RUN_ID/reference-grid.jpg`，跳过 Kie 确认图节点。

## 目录边界

- `TEMP/`：过程文件，可清理，不作为默认续跑状态。
- `OUTPUT/`：正式成片，扁平化保存为 `OUTPUT/RUN_ID.mp4`。
- `DOCS/`：流程和规则。
- `TOOLS/`：自动化脚本。
- `MATERIAL/`：固定角色素材和去重账本。

## 固定流程

1. 预检与建档：读取项目文档，检查 CDP Chrome、Kie API key、Dreamina 视频生成、发布登录态、角色素材、`TEMP/` 和 `OUTPUT/`。
2. 参考选择：没有用户指定参考时，从抖音收藏抽样；进入流程前先做 7 天去重。
3. 参考宫格、导演结构反推与 grid-prompt 规范记录：用 `browser_reference_grid.py` 通过 Playwright-CDP 从 CDP Chrome 视频像素抽 6 帧并生成 `reference-grid.jpg`，执行者根据宫格或帧图反推可见导演结构、身材卖点校准和参考六锁定结论，并写入 `grid-prompt.txt`；`reference-grid.jpg` 后续作为 Dreamina 视频生成的第二张视觉参考输入。
4. 确认图提示词：实际查看宫格或帧图后写 `img prompt`，只写可见画面语言；默认非 TNS 不运行 lint。
5. 确认图：选关键帧，用 `reference_mask.py --grid-report` 优先按抽帧报告自动制作强遮挡参考图，检测缺失或遮挡异常时才用 `--rect` 手工兜底；Kie Nano Banana Pro 1K 先上传 `anna.png` 作为 `@图1`，并在 img prompt 中声明 `@图1` 是同一人的多视角、多表情角色参考图，再上传强遮挡参考图作为 `@图2`，每批固定生成 `A-01/A-02` 两张。
6. 确认图选择：执行者从成功生成的确认图中选择一张进入视频生成，并记录选择原因。
7. 视频生成：执行者综合 `img prompt`、`grid-prompt.txt` 和 `reference-grid.jpg` 重新写成最终 `vid prompt`，上传选中确认图作为 `@图1`、上传参考宫格图作为 `@图2` 后提交 Dreamina 视频。
8. 发布：下载正式 MP4 到 `OUTPUT/RUN_ID.mp4`，上传抖音并设置 `内容由AI生成` 声明。
9. 记录收尾：成功生成正式视频后写入去重账本；发布后只在运行记录中补充发布状态并刷新记录。

## 快速通道备选

- 快速通道只吸收旧 SOP 的通道思想，不恢复旧项目的 TapNow、双人路线、固定画布、7 秒参数、参考图轮选或其他旧工具规则。
- 快速通道只在用户明确说“快速通道”“跳过确认图”或“备用流程”时启用；默认不启用，不因 Kie 失败、时间紧或已有候选文件自动切换。
- 快速通道仍必须完成预检、参考选择或去重、参考宫格、`grid-prompt.txt`、Dreamina 生成、质检、发布和记录。
- 快速通道跳过模块 02 的 Kie 确认图和确认图选择，直接进入模块 03；Dreamina 输入固定为 `@图1 = MATERIAL/fixed-role/anna.png`、`@图2 = TEMP/RUN_ID/reference-grid.jpg`。
- 快速通道 `vid prompt` 必须由 `grid-prompt.txt` 人工重写生成，强调人物身份以 `@图1` 角色卡为准，`@图2` 参考宫格只提供场景、分镜、镜头视角、穿搭版型、动作节奏和封面停顿。
- 快速通道不得使用强遮挡参考图作为 Dreamina 输入；强遮挡参考图只属于 Kie 确认图主流程。
- 快速通道生成失败时，不自动切回主流程；停止并报告实际失败原因与可选下一步。

## 硬阻断

- 参考宫格未通过，不进入提示词或生成。
- 主流程没有可用确认图或未记录选中确认图，不进入视频生成；快速通道显式启用时不要求 `selected_confirmation_image`，但必须有 `MATERIAL/fixed-role/anna.png`、`reference-grid.jpg` 和 `grid-prompt.txt`。
- 视频生成前缺少 `reference-grid.jpg`，或 vid prompt 未把 `@图2` 说明为参考宫格图，不进入 Dreamina 提交。
- 发布前未完成 `内容由AI生成` 声明，不得发布。
- 登录失效、验证码、账号安全、平台风控、上传失败、发布按钮禁用等平台阻断时停止并报告。
