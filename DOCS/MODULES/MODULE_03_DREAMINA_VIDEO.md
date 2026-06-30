# 模块 03：Dreamina 视频生成

## 职责

- 上传模块 02 用户确认后的 Kie 原始图，使用 `derive --mode slow-vid` 生成最终 vid prompt。
- 提交 Dreamina `multimodal2video` 并下载正式 MP4。
- 视频生成后固定等待用户确认发布。

## prompt 边界

- vid prompt 的内容规范只看模块 01，本模块不维护十段式标签、类型集合、人物段、穿搭、镜头、动画、音乐或画质写法。
- `vid-prompt-v1.txt` 必须由 `TOOLS/prompt_lint.py derive` 从 `grid-prompt.txt` 生成，不得在视频阶段临时拼接、解释或二次改写。
- 视频阶段只上传模块 02 选中的 Kie 原始图，并在 prompt 中用 `@图1` 指代。
- 视频阶段不把 `reference-grid.jpg`、参考帧或参考图作为输入；参考宫格只作为模块 01 的人工分析来源。
- Dreamina 视频阶段的图片指代统一使用 `@` 方式，不做脚本转换。
- derive 不通过时回到模块 01 重写 `grid-prompt.txt`，不得在模块 03 临时修补。

## 视频生成

所有任务必须先完成模块 02 的 Kie 确认图生成与选择。提交 Dreamina 前必须确认：

- `selected_confirmation_image` 指向 Kie 下载到本地的原始确认图，并作为 `@图1` 上传。
- `TEMP/RUN_ID/vid-prompt-v1.txt` 由 `prompt_lint.py derive --mode slow-vid` 生成并通过校验。
- 未上传参考图、参考帧或 `reference-grid.jpg`。

命令示例：

```bash
python3 TOOLS/prompt_lint.py derive TEMP/RUN_ID/grid-prompt.txt --mode slow-vid --out TEMP/RUN_ID/vid-prompt-v1.txt
dreamina multimodal2video --image TEMP/RUN_ID/confirm-A-HHMMSS/A-01/SELECTED.png --prompt "$(cat TEMP/RUN_ID/vid-prompt-v1.txt)" --model_version seedance2.0_vip --ratio 9:16 --video_resolution 720p --duration 5
```

遇到非 TNS/安全拦截的生成失败，或 TNS/安全拦截收敛到 `v5` 后仍未生成时，停止并报告 Dreamina 返回状态、已使用输入、`vid prompt` 路径、最高尝试版本和可选下一步。

## 视频后的确认规则

- MP4 通过可解码、竖屏和时长校验后固定在本模块硬停，展示视频、首中尾帧、vid prompt、TNS 记录和是否建议发布；未获用户明确发布确认不得进入模块 04。

## 重试

- Dreamina 命令包含第二个 `--image`、把 `reference-grid.jpg` 作为输入，或 vid prompt 含第二张图片引用时，不得提交 Dreamina；已提交的视频节点一律弃用，不下载、不质检、不发布。
- 视频 prompt 初稿固定为 `vid-prompt-v1.txt`；`v1` 是首次提交，内容必须由 `prompt_lint.py derive` 从 `grid-prompt.txt` 生成。
- 只有 Dreamina 明确返回 TNS/安全拦截且没有生成可下载 MP4 时，才允许继续写 `vid-prompt-v2.txt` 到 `vid-prompt-v5.txt` 逐步收敛并重提。
- TNS 收敛期间仍只使用同一张选中确认图，不得换图、增加第二张图、接入其他路线或兜底工具。
- TNS/安全拦截后的每个收敛版本必须重新人工改写，重新运行 `prompt_lint.py`，lint 通过后才可提交 Dreamina。
- 到 `v5` 仍因 TNS/安全拦截未生成 MP4 时，停止，不发布，并报告 `v1-v5` 的失败摘要和最后可选下一步。
- 网络、登录、积分、参数错误、上传失败、超时、Dreamina 返回非 TNS 失败等不进入 `v2-v5` 收敛，按硬阻断报告。
- 每次 TNS 尝试必须记录版本号、prompt 路径、Dreamina 返回状态、失败原因和是否进入下一版；最终交付时报告最高尝试版本。

## 通过标准

- Dreamina 只收到用户选中的唯一确认图；vid prompt 由 `prompt_lint.py derive` 生成并通过校验。
- vid prompt 不含第二张图片引用或参考图视觉输入语义。
- 下载到的 MP4 可解码、竖屏、约 5-6 秒，并整理为 `OUTPUT/RUN_ID.mp4`。
- 已取得用户发布确认后才可进入模块 04。
