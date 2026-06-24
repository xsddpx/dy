# 模块 03：Dreamina 视频生成

## 职责

- 综合模块 02 的 img prompt、模块 01 的 grid prompt 和参考宫格图，人工重写最终 vid prompt。
- 提交 Dreamina `multimodal2video` 并下载正式 MP4。

## prompt 边界

- img prompt 和 vid prompt 是两个阶段的输入。
- img prompt 用于确认图阶段，使用 `@图1=角色上传图`、`@图2=强遮挡参考图`。
- vid prompt 用于视频阶段，上传模块 02 选中的 Kie 原始确认图和模块 01 的 `reference-grid.jpg`。
- 视频阶段 `@图1` 指代选中的 Kie 原始确认图，提供人物身份、姿态和画面锚点。
- 视频阶段 `@图2` 指代本次参考宫格图，提供场景、分镜、镜头视角、穿搭版型、动作节奏和封面停顿参考。
- Dreamina 视频阶段的图片指代统一使用 `@` 方式，不做脚本转换。
- 确认图阶段的 `@图2` 是强遮挡参考图；视频阶段的 `@图2` 是参考宫格图。两者语义不同，vid prompt 不得沿用确认图阶段强遮挡参考图的语义。
- 执行者必须分析 img prompt 的人物、环境、画面质感，以及 grid prompt 的整体动画、可见导演结构和参考六锁定结论，重新写成新的 vid prompt；不得用脚本做简单合并。

## vid prompt 格式

最终 vid prompt 在 img prompt 三段式基础上增加整体动画和背景音乐：

```text
人物：以 @图1 中的人物和穿搭作为身份、姿态和画面锚点，...
环境：延续 @图1 的空间、光线、材质和主体关系，参考 @图2 中的场景、分镜、镜头视角、穿搭版型、动作节奏和封面停顿，不复刻原视频人物身份、真人脸、账号标识、字幕水印、品牌商标或专有 IP。
整体动画：...
背景音乐：...
其他：真实皮肤纹理，自然光影，真实面料质感，构图稳定，画面物理真实。除背景音乐外，不出现环境声、人声、脚步声、衣料声、镜头声、口播、对白、喘息或音效。
```

- `整体动画：` 必须来自 `grid-prompt.txt` 的动画判断，并吸收其中的姿态、镜头、场景、穿搭、身材描述、动作与封面六锁定结论；最终表达必须与选中确认图不冲突。
- `背景音乐：` 只写音乐风格、节奏和情绪，不写歌词、对白、口播或任何非音乐声音。
- `其他：` 必须明确杜绝音乐以外的其他声音。

## 命令

```bash
dreamina multimodal2video --image TEMP/RUN_ID/confirm-A-HHMMSS/A-01/SELECTED.png --image TEMP/RUN_ID/reference-grid.jpg --prompt "$(cat TEMP/RUN_ID/vid-prompt.txt)" --model_version seedance2.0_vip --ratio 9:16 --video_resolution 720p --duration 5
```

`--duration` 可按本次画面节奏使用 `5` 或 `6`。

## 重试

- 缺少 `reference-grid.jpg`、缺少第二个 `--image`，或 vid prompt 未说明 `@图2` 是参考宫格图时，不得提交 Dreamina；已提交的视频节点一律弃用，不下载、不质检、不上传、不发布。
- 同一确认图和同一 prompt 最多自动提交 2 次，包含第一次提交和最多一次自动收敛或原样重提。
- TNS/安全拦截后的收敛版本必须重新运行 `prompt_lint.py`。

## 通过标准

- Dreamina 命令同时上传选中确认图和 `reference-grid.jpg`。
- Dreamina vid prompt 使用 `@图1` 指代选中确认图，使用 `@图2` 指代参考宫格图。
- vid prompt 已综合 img prompt 和 `grid-prompt.txt` 的整体动画、可见导演结构和参考六锁定结论，不是机械合并。
- vid prompt 使用 `人物：`、`环境：`、`整体动画：`、`背景音乐：`、`其他：` 格式。
- vid prompt 不沿用确认图阶段 `@图2` 的强遮挡参考图语义，不含音乐以外的其他声音。
- 下载到的 MP4 可解码、竖屏、约 5-6 秒，并整理为 `OUTPUT/RUN_ID.mp4`。
