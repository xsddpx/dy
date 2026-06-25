# 模块 03：Dreamina 视频生成

## 职责

- 在默认 `auto/fast` 模式下，根据 `anna.png` 和模块 01 的 grid prompt 人工重写最终 vid prompt。
- 在显式 `slow` 模式下，综合模块 02 的 img prompt 和模块 01 的 grid prompt，人工重写最终 vid prompt；其中模块 02 的 img prompt 已直接来自宫格或帧图分析，不依赖 grid prompt。
- 提交 Dreamina `multimodal2video` 并下载正式 MP4。

## prompt 边界

- img prompt 和 vid prompt 是两个阶段的输入。
- img prompt 用于确认图阶段，使用 `@图1=角色上传图`。
- slow 的 img prompt 直接查看 `reference-grid.jpg` 或帧图生成，重点分析穿搭、环境、人物姿态和镜头关系，不读取或依赖 `grid-prompt.txt`。
- `auto/fast` 视频阶段只上传 `MATERIAL/fixed-role/anna.png`，并在 prompt 中用 `@图1` 指代。
- `slow` 视频阶段只上传模块 02 选中的 Kie 原始图，并在 prompt 中用 `@图1` 指代。
- 视频阶段 `@图1` 指代当前模式唯一上传的图片：`auto/fast` 中是 `anna.png`，`slow` 中是选中的 Kie 原始图。
- 视频阶段不把 `reference-grid.jpg` 作为输入；参考宫格只作为 `grid-prompt.txt` 的文字分析来源，vid prompt 中不保留第二张图片引用。
- `auto` 就是 `fast`，是默认模式；“快速通道”只是兼容叫法。
- “跳过确认图”也是 `fast` 的兼容触发词。
- `slow` 只有用户明确说 `slow`、`慢速模式`、`Kie 确认图`、`确认图流程` 或 `完整确认图流程` 时才启用。
- Dreamina 视频阶段的图片指代统一使用 `@` 方式，不做脚本转换。
- 确认图阶段只上传角色图；视频阶段也只有一张图片输入，vid prompt 不得引入第二张图片语义。
- `auto/fast` 没有 img prompt 输入，执行者必须根据 `anna.png` 的角色身份，以及 `grid-prompt.txt` 的参考类型、可见导演结构重写 vid prompt。
- `slow` 执行者必须分析 img prompt 的人物、穿搭、姿态镜头、环境、画面质感，以及 grid prompt 的参考类型、整体动画、可见导演结构、身材卖点校准和参考六锁定结论，重新写成新的 vid prompt；不得用脚本做简单合并。
- 任何模式都不得把参考图、参考帧或参考宫格图作为 Dreamina 输入。
- 最终 vid prompt 必须是 Dreamina 可直接执行的画面描述，不得出现 `grid-prompt.txt`、`reference-grid`、`参考宫格`、`同时吸收`、`吸收 grid`、`根据 grid`、`根据文档`、`上述分析`、`文件`、`流程`、`节点` 等内部来源词或解释性词。

## vid prompt 格式

最终 vid prompt 必须使用六段式结构：

```text
人物：以 @图1 中的人物作为身份、五官、发型、脸型和稳定身材比例依据，...
环境：现代室内走廊/电梯厅，浅米色墙面、亮面地砖、顶部格栅吊顶和柔和顶灯，人物位于走廊中央，背景有干净纵深线条，不出现原视频人物身份、真人脸、账号标识、字幕水印、品牌商标或专有 IP。
卖点与锁定：...
整体动画：视频类型为穿搭展示，次类型为健身运动；...
背景音乐：...
其他：真实皮肤纹理，自然光影，真实面料质感，构图稳定，画面物理真实。除背景音乐外，不出现环境声、人声、脚步声、衣料声、镜头声、口播、对白、喘息或音效。
```

- `人物：` `auto/fast` 以 `anna.png` 作为 `@图1` 的身份、五官、发型、脸型和稳定身材比例依据；穿搭、动作、场景来自本次参考类型和导演结构，不得写“以 @图1 中的穿搭作为依据”或同义表达。`slow` 以选中图作为 `@图1` 的身份、姿态和画面锚点。
- `环境：` 必须直接写入空间、光线、材质和主体关系，不写文件名、来源说明或“吸收/根据某文件”的解释性表达；不复刻原视频人物身份、真人脸、账号标识、字幕水印、品牌商标或专有 IP。
- `卖点与锁定：` 必须写入身材卖点校准和参考六锁定的最终取舍，包括穿搭版型、领口与上身轮廓、面料张力、腰线、腰胯比例、姿态、镜头裁切、动作重点和封面停顿；表达只使用可见画面语言，不写流程说明。
- `整体动画：` 必须以 `视频类型为主类型，次类型为次类型；` 开头；次类型为无时写 `视频类型为主类型，次类型为无；`。vid prompt 必须围绕约 6 秒成片重新编排动画，不按参考原时长逐秒照搬。随后写清连续动作、手部路径、身体重心变化、镜头距离、角度、运镜、节奏点、参考表情节奏和结尾停顿；`auto/fast` 最终表达必须与 `anna.png` 角色身份不冲突，`slow` 最终表达必须与选中图不冲突。
- 表情写法参考优先，承接模块 01 中开场、中段、结尾的眼神、嘴角、眉眼和脸部状态；微笑允许存在，但应与参考动作和场景匹配，不把“最后微笑停顿”写成固定收尾句式。
- `背景音乐：` 只写音乐风格、节奏和情绪，不写歌词、对白、口播或任何非音乐声音。
- `其他：` 写真实皮肤纹理、自然光影、真实面料质感、构图稳定、画面物理真实，并必须明确杜绝音乐以外的其他声音。

## auto/fast 命令

```bash
dreamina multimodal2video --image MATERIAL/fixed-role/anna.png --prompt "$(cat TEMP/RUN_ID/vid-prompt-v1.txt)" --model_version seedance2.0_vip --ratio 9:16 --video_resolution 720p --duration 5
```

`--duration` 可按本次画面节奏使用 `5` 或 `6`。

## auto/fast 默认模式

`auto` 就是 `fast`，是 `/dy`、`dy`、`$dy`、`dy 开始`、`今天日更` 的默认执行模式；`fast` 和 `快速通道` 是同一模式的兼容叫法。
`跳过确认图` 也触发 `fast`。

`auto/fast` 必须先完成模块 00 和模块 01，通过参考宫格并写好 `grid-prompt.txt`。提交 Dreamina 前必须确认：

- `MATERIAL/fixed-role/anna.png` 存在，并作为 `@图1` 上传。
- `TEMP/RUN_ID/grid-prompt.txt` 存在，且已记录参考类型识别、可见导演结构、身材卖点校准和参考六锁定结论。
- `vid prompt` 已由 `grid-prompt.txt` 人工重写为可直接执行的 Dreamina 画面描述，说明人物身份、五官、发型、脸型和稳定身材比例以 `@图1` 角色卡为准，穿搭、动作、场景和表情节奏来自本次参考类型与导演结构；最终 prompt 不得出现文件名、流程说明、来源说明或“吸收/根据某文件”的表达。
- 未上传任何参考图、参考帧或参考宫格图。
- 未上传 `reference-grid.jpg`；参考宫格不作为 Dreamina 视频视觉输入。

## slow 显式模式

`slow` 只有用户明确说 `slow`、`慢速模式`、`Kie 确认图`、`确认图流程` 或 `完整确认图流程` 时才启用。`slow` 必须先完成模块 02 的 Kie 确认图生成与选择。提交 Dreamina 前必须确认：

- `selected_confirmation_image` 指向 Kie 下载到本地的原始确认图，并作为 `@图1` 上传。
- `TEMP/RUN_ID/grid-prompt.txt` 存在，且已记录参考类型识别、可见导演结构、身材卖点校准和参考六锁定结论。
- `vid prompt` 已综合 img prompt 和 `grid-prompt.txt` 人工重写为可直接执行的 Dreamina 画面描述，已显式写入视频类型并承接参考表情节奏，且不含第二张图片引用、文件名、流程说明或确认图阶段解释。
- 未上传参考图、参考帧或 `reference-grid.jpg`。

slow 命令示例：

```bash
dreamina multimodal2video --image TEMP/RUN_ID/confirm-A-HHMMSS/A-01/SELECTED.png --prompt "$(cat TEMP/RUN_ID/vid-prompt-v1.txt)" --model_version seedance2.0_vip --ratio 9:16 --video_resolution 720p --duration 5
```

任何模式遇到非 TNS/安全拦截的生成失败，或 TNS/安全拦截收敛到 `v5` 后仍未生成时，都不自动切换到另一个模式；停止并报告 Dreamina 返回状态、已使用输入、`vid prompt` 路径、最高尝试版本和可选下一步。

## 重试

- Dreamina 命令包含第二个 `--image`、把 `reference-grid.jpg` 作为输入，或 vid prompt 含第二张图片引用时，不得提交 Dreamina；已提交的视频节点一律弃用，不下载、不质检、不发布。
- 视频 prompt 初稿固定为 `vid-prompt-v1.txt`；`v1` 是首次提交。
- 只有 Dreamina 明确返回 TNS/安全拦截且没有生成可下载 MP4 时，才允许继续写 `vid-prompt-v2.txt` 到 `vid-prompt-v5.txt` 逐步收敛并重提。
- `auto/fast` 在 TNS 收敛期间仍只使用同一张 `MATERIAL/fixed-role/anna.png`；`slow` 仍只使用同一张选中确认图。不得因 TNS 切换模式、换图、增加第二张图、接入其他路线或兜底工具。
- TNS/安全拦截后的每个收敛版本必须重新人工改写，重新运行 `prompt_lint.py`，lint 通过后才可提交 Dreamina。
- 到 `v5` 仍因 TNS/安全拦截未生成 MP4 时，停止，不发布，并报告 `v1-v5` 的失败摘要和最后可选下一步。
- 网络、登录、积分、参数错误、上传失败、超时、Dreamina 返回非 TNS 失败等不进入 `v2-v5` 收敛，按硬阻断报告。
- 每次 TNS 尝试必须记录版本号、prompt 路径、Dreamina 返回状态、失败原因和是否进入下一版；最终交付时报告最高尝试版本。

## 通过标准

- `auto/fast` Dreamina 命令只上传 `MATERIAL/fixed-role/anna.png`；`slow` Dreamina 命令只上传选中图。
- `auto/fast` Dreamina vid prompt 使用 `@图1` 指代 `anna.png`；`slow` 使用 `@图1` 指代选中图；两种模式都不得把参考宫格写成图片输入。
- `auto/fast` vid prompt 已根据角色卡和 `grid-prompt.txt` 人工重写；`slow` vid prompt 已综合 img prompt 和 `grid-prompt.txt` 人工重写。两种模式都不得机械合并。
- vid prompt 使用 `人物：`、`环境：`、`卖点与锁定：`、`整体动画：`、`背景音乐：`、`其他：` 格式。
- `整体动画：` 已以 `视频类型为...，次类型为...；` 开头，类型来自模块 01 的合法集合。
- `整体动画：` 已承接模块 01 的参考表情节奏，表情随动作、镜头距离和场景自然变化，不把微笑作为默认模板。
- vid prompt 不含第二张图片引用，不引入参考图视觉输入语义，不含文件名、流程说明、来源说明或音乐以外的其他声音。
- 下载到的 MP4 可解码、竖屏、约 5-6 秒，并整理为 `OUTPUT/RUN_ID.mp4`。
