# 模块 03：Dreamina 视频生成

## 职责

- 在默认 `auto/fast` 模式下，根据 `anna.png` 和模块 01 的 grid prompt 人工重写最终 vid prompt。
- 在显式 `slow` 模式下，综合模块 02 的 img prompt 和模块 01 的 grid prompt，人工重写最终 vid prompt。
- 提交 Dreamina `multimodal2video` 并下载正式 MP4。

## prompt 边界

- img prompt 和 vid prompt 是两个阶段的输入。
- img prompt 用于确认图阶段，使用 `@图1=角色上传图`、`@图2=强遮挡参考图`。
- `auto/fast` 视频阶段只上传 `MATERIAL/fixed-role/anna.png`，并在 prompt 中用 `@图1` 指代。
- `slow` 视频阶段只上传模块 02 选中的 Kie 原始图，并在 prompt 中用 `@图1` 指代。
- 视频阶段 `@图1` 指代当前模式唯一上传的图片：`auto/fast` 中是 `anna.png`，`slow` 中是选中的 Kie 原始图。
- 视频阶段不把 `reference-grid.jpg` 作为输入；参考宫格只作为 `grid-prompt.txt` 的文字分析来源，vid prompt 中不保留 `@图2`。
- `auto` 就是 `fast`，是默认模式；“快速通道”只是兼容叫法。
- “跳过确认图”也是 `fast` 的兼容触发词。
- `slow` 只有用户明确说 `slow`、`慢速模式`、`Kie 确认图`、`确认图流程` 或 `完整确认图流程` 时才启用。
- Dreamina 视频阶段的图片指代统一使用 `@` 方式，不做脚本转换。
- 确认图阶段的 `@图2` 是强遮挡参考图；视频阶段没有 `@图2`，vid prompt 不得沿用确认图阶段强遮挡参考图的语义。
- `auto/fast` 没有 img prompt 输入，执行者必须只根据 `anna.png` 的角色身份和 `grid-prompt.txt` 的可见导演结构重写 vid prompt。
- `slow` 执行者必须分析 img prompt 的人物、环境、画面质感，以及 grid prompt 的整体动画、可见导演结构、身材卖点校准和参考六锁定结论，重新写成新的 vid prompt；不得用脚本做简单合并。
- 任何模式都不得把强遮挡参考图或参考宫格图作为 Dreamina 输入。

## vid prompt 格式

最终 vid prompt 必须使用六段式结构：

```text
人物：以 @图1 中的人物和穿搭作为身份、五官、发型、姿态、穿搭和稳定身材比例依据，...
环境：延续 @图1 的空间、光线、材质和主体关系，吸收 grid-prompt.txt 中的场景、分镜、镜头视角、穿搭版型、动作节奏和封面停顿，不复刻原视频人物身份、真人脸、账号标识、字幕水印、品牌商标或专有 IP。
卖点与锁定：...
整体动画：...
背景音乐：...
其他：真实皮肤纹理，自然光影，真实面料质感，构图稳定，画面物理真实。除背景音乐外，不出现环境声、人声、脚步声、衣料声、镜头声、口播、对白、喘息或音效。
```

- `人物：` `auto/fast` 以 `anna.png` 作为 `@图1` 的身份、五官、发型和稳定身材比例依据；`slow` 以选中图作为 `@图1` 的身份、姿态和画面锚点。
- `环境：` 必须写入空间、光线、材质和主体关系，只吸收 `grid-prompt.txt` 的文字分析结论，不复刻原视频人物身份、真人脸、账号标识、字幕水印、品牌商标或专有 IP。
- `卖点与锁定：` 必须写入身材卖点校准和参考六锁定的最终取舍，包括穿搭版型、领口与上身轮廓、面料张力、腰线、腰胯比例、姿态、镜头裁切、动作重点和封面停顿；表达只使用可见画面语言，不写流程说明。
- `整体动画：` 必须来自 `grid-prompt.txt` 的动画判断，写清连续动作、手部路径、身体重心变化、镜头距离、角度、运镜、节奏点和结尾停顿；`auto/fast` 最终表达必须与 `anna.png` 角色身份不冲突，`slow` 最终表达必须与选中图不冲突。
- `背景音乐：` 只写音乐风格、节奏和情绪，不写歌词、对白、口播或任何非音乐声音。
- `其他：` 写真实皮肤纹理、自然光影、真实面料质感、构图稳定、画面物理真实，并必须明确杜绝音乐以外的其他声音。

## auto/fast 命令

```bash
dreamina multimodal2video --image MATERIAL/fixed-role/anna.png --prompt "$(cat TEMP/RUN_ID/vid-prompt.txt)" --model_version seedance2.0_vip --ratio 9:16 --video_resolution 720p --duration 5
```

`--duration` 可按本次画面节奏使用 `5` 或 `6`。

## auto/fast 默认模式

`auto` 就是 `fast`，是 `/dy`、`dy`、`$dy`、`dy 开始`、`今天日更` 的默认执行模式；`fast` 和 `快速通道` 是同一模式的兼容叫法。
`跳过确认图` 也触发 `fast`。

`auto/fast` 必须先完成模块 00 和模块 01，通过参考宫格并写好 `grid-prompt.txt`。提交 Dreamina 前必须确认：

- `MATERIAL/fixed-role/anna.png` 存在，并作为 `@图1` 上传。
- `TEMP/RUN_ID/grid-prompt.txt` 存在，且已记录可见导演结构、身材卖点校准和参考六锁定结论。
- `vid prompt` 已由 `grid-prompt.txt` 人工重写，说明人物身份、五官、发型和稳定身材比例以 `@图1` 角色卡为准；参考宫格只作为文字分析来源，用于场景、分镜、镜头视角、穿搭版型、动作节奏、身材卖点校准、参考六锁定和封面停顿，不复刻原视频人物身份、真人脸、账号标识、字幕水印、品牌商标或专有 IP。
- 未上传强遮挡参考图；强遮挡参考图只属于 slow Kie 确认图流程。
- 未上传 `reference-grid.jpg`；参考宫格不作为 Dreamina 视频视觉输入。

## slow 显式模式

`slow` 只有用户明确说 `slow`、`慢速模式`、`Kie 确认图`、`确认图流程` 或 `完整确认图流程` 时才启用。`slow` 必须先完成模块 02 的 Kie 确认图生成与选择。提交 Dreamina 前必须确认：

- `selected_confirmation_image` 指向 Kie 下载到本地的原始确认图，并作为 `@图1` 上传。
- `TEMP/RUN_ID/grid-prompt.txt` 存在，且已记录可见导演结构、身材卖点校准和参考六锁定结论。
- `vid prompt` 已综合 img prompt 和 `grid-prompt.txt` 人工重写，且不含 `@图2`。
- 未上传强遮挡参考图或 `reference-grid.jpg`。

slow 命令示例：

```bash
dreamina multimodal2video --image TEMP/RUN_ID/confirm-A-HHMMSS/A-01/SELECTED.png --prompt "$(cat TEMP/RUN_ID/vid-prompt.txt)" --model_version seedance2.0_vip --ratio 9:16 --video_resolution 720p --duration 5
```

任何模式生成失败时，都不自动切换到另一个模式；停止并报告 Dreamina 返回状态、已使用输入、`vid prompt` 路径和可选下一步。

## 重试

- Dreamina 命令包含第二个 `--image`、把 `reference-grid.jpg` 作为输入，或 vid prompt 含 `@图2` 时，不得提交 Dreamina；已提交的视频节点一律弃用，不下载、不质检、不发布。
- `auto/fast` 同一角色卡和同一 prompt 最多自动提交 2 次，包含第一次提交和最多一次自动收敛或原样重提。
- `slow` 同一确认图和同一 prompt 最多自动提交 2 次，包含第一次提交和最多一次自动收敛或原样重提。
- TNS/安全拦截后的收敛版本必须重新运行 `prompt_lint.py`。

## 通过标准

- `auto/fast` Dreamina 命令只上传 `MATERIAL/fixed-role/anna.png`；`slow` Dreamina 命令只上传选中图。
- `auto/fast` Dreamina vid prompt 使用 `@图1` 指代 `anna.png`；`slow` 使用 `@图1` 指代选中图；两种模式都不得把参考宫格写作 `@图2`。
- `auto/fast` vid prompt 已根据角色卡和 `grid-prompt.txt` 人工重写；`slow` vid prompt 已综合 img prompt 和 `grid-prompt.txt` 人工重写。两种模式都不得机械合并。
- vid prompt 使用 `人物：`、`环境：`、`卖点与锁定：`、`整体动画：`、`背景音乐：`、`其他：` 格式。
- vid prompt 不含 `@图2`，不沿用确认图阶段强遮挡参考图语义，不含音乐以外的其他声音。
- 下载到的 MP4 可解码、竖屏、约 5-6 秒，并整理为 `OUTPUT/RUN_ID.mp4`。
