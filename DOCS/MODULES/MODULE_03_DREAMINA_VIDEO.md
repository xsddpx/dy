# 模块 03：Dreamina 视频生成

## 职责

- 在默认 `auto/fast` 模式下，上传 `anna.png`，直接使用模块 01 的 `grid-prompt.txt` 作为最终 vid prompt。
- 在显式 `slow` 模式下，上传模块 02 用户确认后的 Kie 原始图，从 `grid-prompt.txt` 删除人物段中的 anna 多视角角色卡声明后作为最终 vid prompt。
- 提交 Dreamina `multimodal2video` 并下载正式 MP4。

## prompt 边界

- vid prompt 的内容规范只看模块 01，本模块不维护十段式标签、类型集合、人物段、穿搭、镜头、动画、音乐或画质写法。
- `grid-prompt.txt` 是 fast 的 Dreamina v1 最终视频 prompt 本体，也是 slow 视频 prompt 的直接派生来源；它不是分析记录、规则库或待拼装草稿。
- `auto/fast` 如运行记录需要保留 `vid-prompt-v1.txt`，它必须是 `grid-prompt.txt` 的逐字副本，不得二次整理、增删段落或改写语义。
- `slow` 的 `vid-prompt-v1.txt` 从 `grid-prompt.txt` 派生，只删除人物段中“@图1 是同一位成年女性的多视角、多表情角色参考图...”这类角色卡声明；其余人物身份一致性文本和其他九段必须保持一致。
- `auto/fast` 视频阶段只上传 `MATERIAL/fixed-role/anna.png`，并在 prompt 中用 `@图1` 指代。
- `slow` 视频阶段只上传模块 02 选中的 Kie 原始图，并在 prompt 中用 `@图1` 指代。
- 视频阶段 `@图1` 指代当前模式唯一上传的图片：`auto/fast` 中是 `anna.png`，`slow` 中是选中的 Kie 原始图。
- 视频阶段不把 `reference-grid.jpg`、参考帧或参考图作为输入；参考宫格只作为模块 01 的人工分析来源。
- `auto` 就是 `fast`，是默认模式；“快速通道”和“跳过确认图”只是 `fast` 的兼容叫法。
- `slow` 只有用户明确说 `slow`、`慢速模式`、`Kie 确认图`、`确认图流程` 或 `完整确认图流程` 时才启用。
- Dreamina 视频阶段的图片指代统一使用 `@` 方式，不做脚本转换。
- 最终 vid prompt 必须先通过 `prompt_lint.py`；fast 使用默认 `--video-mode fast`，slow 必须使用 `--video-mode slow`，不通过时回到模块 01 重写或按 slow 派生规则删除角色卡声明，不得在视频阶段临时拼接或解释。

## auto/fast 命令

```bash
cp TEMP/RUN_ID/grid-prompt.txt TEMP/RUN_ID/vid-prompt-v1.txt
dreamina multimodal2video --image MATERIAL/fixed-role/anna.png --prompt "$(cat TEMP/RUN_ID/vid-prompt-v1.txt)" --model_version seedance2.0_vip --ratio 9:16 --video_resolution 720p --duration 5
```

`--duration` 可按本次画面节奏使用 `5` 或 `6`。

## auto/fast 默认模式

`auto/fast` 必须先完成模块 00 和模块 01，通过参考宫格并写好 `grid-prompt.txt`。提交 Dreamina 前必须确认：

- `MATERIAL/fixed-role/anna.png` 存在，并作为 `@图1` 上传。
- `TEMP/RUN_ID/grid-prompt.txt` 存在，且通过 `prompt_lint.py --video-mode fast`。
- 如存在 `TEMP/RUN_ID/vid-prompt-v1.txt`，其内容与 `grid-prompt.txt` 逐字一致。
- `vid-prompt-v1.txt` 的人物段保留 anna 多视角、多表情角色卡声明。
- 未上传任何参考图、参考帧或参考宫格图。

## slow 显式模式

`slow` 只有用户明确说 `slow`、`慢速模式`、`Kie 确认图`、`确认图流程` 或 `完整确认图流程` 时才启用。`slow` 必须先完成模块 02 的 Kie 确认图生成与选择。提交 Dreamina 前必须确认：

- `selected_confirmation_image` 指向 Kie 下载到本地的原始确认图，并作为 `@图1` 上传。
- `TEMP/RUN_ID/grid-prompt.txt` 存在，且通过 `prompt_lint.py --video-mode fast`。
- `TEMP/RUN_ID/vid-prompt-v1.txt` 只比 `grid-prompt.txt` 少人物段中的 anna 多视角角色卡声明，其余文本保持一致，并通过 `prompt_lint.py --video-mode slow`。
- 未上传参考图、参考帧或 `reference-grid.jpg`。

slow 命令示例：

```bash
# 从 grid-prompt.txt 复制生成 vid-prompt-v1.txt，并只删除人物段中的 anna 多视角角色卡声明。
dreamina multimodal2video --image TEMP/RUN_ID/confirm-A-HHMMSS/A-01/SELECTED.png --prompt "$(cat TEMP/RUN_ID/vid-prompt-v1.txt)" --model_version seedance2.0_vip --ratio 9:16 --video_resolution 720p --duration 5
```

任何模式遇到非 TNS/安全拦截的生成失败，或 TNS/安全拦截收敛到 `v5` 后仍未生成时，都不自动切换到另一个模式；停止并报告 Dreamina 返回状态、已使用输入、`vid prompt` 路径、最高尝试版本和可选下一步。

## 重试

- Dreamina 命令包含第二个 `--image`、把 `reference-grid.jpg` 作为输入，或 vid prompt 含第二张图片引用时，不得提交 Dreamina；已提交的视频节点一律弃用，不下载、不质检、不发布。
- 视频 prompt 初稿固定为 `vid-prompt-v1.txt`；`v1` 是首次提交，内容必须来自 `grid-prompt.txt`，其中 slow 只允许删除人物段中的 anna 多视角角色卡声明。
- 只有 Dreamina 明确返回 TNS/安全拦截且没有生成可下载 MP4 时，才允许继续写 `vid-prompt-v2.txt` 到 `vid-prompt-v5.txt` 逐步收敛并重提。
- `auto/fast` 在 TNS 收敛期间仍只使用同一张 `MATERIAL/fixed-role/anna.png`；`slow` 仍只使用同一张选中确认图。不得因 TNS 切换模式、换图、增加第二张图、接入其他路线或兜底工具。
- TNS/安全拦截后的每个收敛版本必须重新人工改写，按当前视频模式重新运行 `prompt_lint.py --video-mode fast|slow`，lint 通过后才可提交 Dreamina。
- 到 `v5` 仍因 TNS/安全拦截未生成 MP4 时，停止，不发布，并报告 `v1-v5` 的失败摘要和最后可选下一步。
- 网络、登录、积分、参数错误、上传失败、超时、Dreamina 返回非 TNS 失败等不进入 `v2-v5` 收敛，按硬阻断报告。
- 每次 TNS 尝试必须记录版本号、prompt 路径、Dreamina 返回状态、失败原因和是否进入下一版；最终交付时报告最高尝试版本。

## 通过标准

- `auto/fast` Dreamina 命令只上传 `MATERIAL/fixed-role/anna.png`；`slow` Dreamina 命令只上传选中图。
- `auto/fast` Dreamina vid prompt 使用 `@图1` 指代 `anna.png`；`slow` 使用 `@图1` 指代选中图；两种模式都不得把参考宫格写成图片输入。
- `auto/fast` vid prompt 直接来自模块 01 的 `grid-prompt.txt`，`vid-prompt-v1.txt` 如存在则与其逐字一致，并已通过 `prompt_lint.py --video-mode fast`。
- `slow` vid prompt 从模块 01 的 `grid-prompt.txt` 派生，只删除人物段中的 anna 多视角角色卡声明，并已通过 `prompt_lint.py --video-mode slow`。
- vid prompt 不含第二张图片引用，不引入参考图视觉输入语义。
- 下载到的 MP4 可解码、竖屏、约 5-6 秒，并整理为 `OUTPUT/RUN_ID.mp4`。
