# 模块 03：Dreamina 视频生成

## 职责

- 在默认 `auto/fast` 模式下，上传 `anna.png`，直接使用模块 01 的 `grid-prompt.txt` 作为最终 vid prompt。
- 在显式 `slow` 模式下，上传模块 02 用户确认后的 Kie 原始图，仍直接使用同一份 `grid-prompt.txt` 作为最终 vid prompt。
- 提交 Dreamina `multimodal2video` 并下载正式 MP4。

## prompt 边界

- `grid-prompt.txt` 是 Dreamina v1 的最终视频 prompt 本体，不是分析记录、规则库或待拼装草稿。
- 如运行记录需要保留 `vid-prompt-v1.txt`，它必须是 `grid-prompt.txt` 的逐字副本，不得二次整理、增删段落或改写语义。
- `auto/fast` 视频阶段只上传 `MATERIAL/fixed-role/anna.png`，并在 prompt 中用 `@图1` 指代。
- `slow` 视频阶段只上传模块 02 选中的 Kie 原始图，并在 prompt 中用 `@图1` 指代。
- 视频阶段 `@图1` 指代当前模式唯一上传的图片：`auto/fast` 中是 `anna.png`，`slow` 中是选中的 Kie 原始图。
- 视频阶段不把 `reference-grid.jpg`、参考帧或参考图作为输入；参考宫格只作为模块 01 的人工分析来源。
- `auto` 就是 `fast`，是默认模式；“快速通道”和“跳过确认图”只是 `fast` 的兼容叫法。
- `slow` 只有用户明确说 `slow`、`慢速模式`、`Kie 确认图`、`确认图流程` 或 `完整确认图流程` 时才启用。
- Dreamina 视频阶段的图片指代统一使用 `@` 方式，不做脚本转换。
- 最终 vid prompt 不得出现文件名、来源说明、流程说明、旧参考类型字段、合规说明、平台解释、第二张图片引用或“根据/融合/吸收”等解释性表达。

## vid prompt 格式

最终 vid prompt 必须使用十段式结构：

- `人物：`
- `视频类型：`
- `穿搭：`
- `姿态镜头：`
- `环境：`
- `卖点与锁定：`
- `表情节奏：`
- `整体动画：`
- `背景音乐：`
- `其他：`

- `人物：` 来自模块 01 的固定人物段。`auto/fast` 以 `anna.png` 作为 `@图1` 的身份、五官、发型、脸型和稳定身材比例依据；穿搭、动作、场景来自本次参考分析，不得写“以 @图1 中的穿搭作为依据”或同义表达。`slow` 以选中图作为 `@图1` 的身份、姿态和画面锚点，并与十段式 prompt 保持一致。
- `视频类型：` 必须写主类型和次类型，主类型、次类型只允许使用模块 01 的类型集合，次类型可写 `无`。
- 每段冒号后都必须写最终可执行内容，不得保留省略号、尖括号占位、条件分支或模板说明。
- `穿搭：`、`姿态镜头：`、`环境：`、`卖点与锁定：`、`表情节奏：`、`整体动画：`、`背景音乐：`、`其他：` 直接沿用模块 01 最终文本，不在视频阶段重组。
- `整体动画：` 必须写清约 5-6 秒连续动作、手部路径、身体重心变化、镜头距离、角度、运镜、节奏点和结尾停顿；`auto/fast` 最终表达必须与 `anna.png` 角色身份不冲突，`slow` 最终表达必须与选中图不冲突。
- `表情节奏：` 必须承接参考的开场、中段、结尾眼神和脸部状态；微笑允许存在，但应与参考动作和场景匹配，不把“最后微笑停顿”写成固定收尾句式。
- `背景音乐：` 只写音乐风格、节奏和情绪，不写歌词、对白、口播或任何非音乐声音。
- `其他：` 只写真实皮肤纹理、自然光影、真实面料质感、穿搭轮廓清晰、腰线可见、构图稳定和画面物理真实。

## auto/fast 命令

```bash
cp TEMP/RUN_ID/grid-prompt.txt TEMP/RUN_ID/vid-prompt-v1.txt
dreamina multimodal2video --image MATERIAL/fixed-role/anna.png --prompt "$(cat TEMP/RUN_ID/vid-prompt-v1.txt)" --model_version seedance2.0_vip --ratio 9:16 --video_resolution 720p --duration 5
```

`--duration` 可按本次画面节奏使用 `5` 或 `6`。

## auto/fast 默认模式

`auto/fast` 必须先完成模块 00 和模块 01，通过参考宫格并写好 `grid-prompt.txt`。提交 Dreamina 前必须确认：

- `MATERIAL/fixed-role/anna.png` 存在，并作为 `@图1` 上传。
- `TEMP/RUN_ID/grid-prompt.txt` 存在，且已记录十段式最终 vid prompt。
- 如存在 `TEMP/RUN_ID/vid-prompt-v1.txt`，其内容与 `grid-prompt.txt` 逐字一致。
- 最终 prompt 不含第二张图片引用、文件名、流程说明、来源说明、合规说明、平台解释或“吸收/根据某文件”的表达。
- 未上传任何参考图、参考帧或参考宫格图。

## slow 显式模式

`slow` 只有用户明确说 `slow`、`慢速模式`、`Kie 确认图`、`确认图流程` 或 `完整确认图流程` 时才启用。`slow` 必须先完成模块 02 的 Kie 确认图生成与选择。提交 Dreamina 前必须确认：

- `selected_confirmation_image` 指向 Kie 下载到本地的原始确认图，并作为 `@图1` 上传。
- `TEMP/RUN_ID/grid-prompt.txt` 存在，且已记录十段式最终 vid prompt。
- 如存在 `TEMP/RUN_ID/vid-prompt-v1.txt`，其内容与 `grid-prompt.txt` 逐字一致。
- 最终 prompt 已显式写入 `视频类型：` 和 `表情节奏：`，且不含第二张图片引用、文件名、流程说明、确认图阶段解释、合规说明或平台解释。
- 未上传参考图、参考帧或 `reference-grid.jpg`。

slow 命令示例：

```bash
cp TEMP/RUN_ID/grid-prompt.txt TEMP/RUN_ID/vid-prompt-v1.txt
dreamina multimodal2video --image TEMP/RUN_ID/confirm-A-HHMMSS/A-01/SELECTED.png --prompt "$(cat TEMP/RUN_ID/vid-prompt-v1.txt)" --model_version seedance2.0_vip --ratio 9:16 --video_resolution 720p --duration 5
```

任何模式遇到非 TNS/安全拦截的生成失败，或 TNS/安全拦截收敛到 `v5` 后仍未生成时，都不自动切换到另一个模式；停止并报告 Dreamina 返回状态、已使用输入、`vid prompt` 路径、最高尝试版本和可选下一步。

## 重试

- Dreamina 命令包含第二个 `--image`、把 `reference-grid.jpg` 作为输入，或 vid prompt 含第二张图片引用时，不得提交 Dreamina；已提交的视频节点一律弃用，不下载、不质检、不发布。
- 视频 prompt 初稿固定为 `vid-prompt-v1.txt`；`v1` 是首次提交，内容必须来自 `grid-prompt.txt`。
- 只有 Dreamina 明确返回 TNS/安全拦截且没有生成可下载 MP4 时，才允许继续写 `vid-prompt-v2.txt` 到 `vid-prompt-v5.txt` 逐步收敛并重提。
- `auto/fast` 在 TNS 收敛期间仍只使用同一张 `MATERIAL/fixed-role/anna.png`；`slow` 仍只使用同一张选中确认图。不得因 TNS 切换模式、换图、增加第二张图、接入其他路线或兜底工具。
- TNS/安全拦截后的每个收敛版本必须重新人工改写，重新运行 `prompt_lint.py`，lint 通过后才可提交 Dreamina。
- 到 `v5` 仍因 TNS/安全拦截未生成 MP4 时，停止，不发布，并报告 `v1-v5` 的失败摘要和最后可选下一步。
- 网络、登录、积分、参数错误、上传失败、超时、Dreamina 返回非 TNS 失败等不进入 `v2-v5` 收敛，按硬阻断报告。
- 每次 TNS 尝试必须记录版本号、prompt 路径、Dreamina 返回状态、失败原因和是否进入下一版；最终交付时报告最高尝试版本。

## 通过标准

- `auto/fast` Dreamina 命令只上传 `MATERIAL/fixed-role/anna.png`；`slow` Dreamina 命令只上传选中图。
- `auto/fast` Dreamina vid prompt 使用 `@图1` 指代 `anna.png`；`slow` 使用 `@图1` 指代选中图；两种模式都不得把参考宫格写成图片输入。
- vid prompt 使用 `人物：`、`视频类型：`、`穿搭：`、`姿态镜头：`、`环境：`、`卖点与锁定：`、`表情节奏：`、`整体动画：`、`背景音乐：`、`其他：` 十段式。
- `视频类型：` 已写合法主类型和次类型，`表情节奏：` 已承接模块 01 的参考表情节奏。
- vid prompt 不含第二张图片引用，不引入参考图视觉输入语义，不含文件名、流程说明、来源说明、合规说明、平台解释、直白身材词或音乐以外的其他声音。
- 下载到的 MP4 可解码、竖屏、约 5-6 秒，并整理为 `OUTPUT/RUN_ID.mp4`。
