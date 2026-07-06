# 模块 02：Dreamina 视频生成

## 职责

- 在默认 `auto/fast` 模式下，上传 `anna.png`，使用 `derive --mode fast` 生成最终 vid prompt。
- 提交 Dreamina `multimodal2video` 并下载正式 MP4。
- 执行视频后的基础质检、默认自动发布路由和确认分支规则。

## prompt 边界

- vid prompt 的内容规范只看模块 01，本模块不维护十段式标签、类型集合、人物段、穿搭、镜头、动画、音乐或画质写法。
- `vid-prompt-v1.txt` 必须由 `TOOLS/prompt_lint.py derive` 从 `grid-prompt.txt` 生成，不得在视频阶段临时拼接、解释或二次改写。
- `auto/fast` 视频阶段只上传 `MATERIAL/fixed-role/anna.png`，并在 prompt 中用 `@图1` 指代。
- 视频阶段固定使用 `MATERIAL/fixed-role/anna.png` 作为唯一图片输入。
- Dreamina 视频阶段的图片指代统一使用 `@` 方式，不做脚本转换。
- derive 校验通过后进入视频提交；校验失败时回到模块 01 重写 `grid-prompt.txt`。

## auto/fast 命令

```bash
python3 TOOLS/prompt_lint.py derive TEMP/RUN_ID/grid-prompt.txt --mode fast --out TEMP/RUN_ID/vid-prompt-v1.txt
dreamina multimodal2video --image MATERIAL/fixed-role/anna.png --prompt "$(cat TEMP/RUN_ID/vid-prompt-v1.txt)" --model_version seedance2.0_vip --ratio 9:16 --video_resolution 720p --duration 5
```

`--duration` 可按本次画面节奏使用 `5` 或 `6`。

## auto/fast 默认模式

`auto/fast` 必须先完成模块 01 并写好 `grid-prompt.txt`。默认不执行模块 00；只有遇到环境问题或用户明确要求修环境时才读取环境修复模块。提交 Dreamina 前必须确认：

- `MATERIAL/fixed-role/anna.png` 存在，并作为 `@图1` 上传。
- `TEMP/RUN_ID/vid-prompt-v1.txt` 由 `prompt_lint.py derive --mode fast` 生成，内容与 `grid-prompt.txt` 逐字一致。
- `vid-prompt-v1.txt` 的人物段保留 anna 多视角、多表情角色卡声明。
- Dreamina 命令只包含 `MATERIAL/fixed-role/anna.png` 这一项图片输入。

遇到非 TNS/安全拦截的生成失败，或 TNS/安全拦截收敛到 `v5` 后仍未生成时，停止并报告 Dreamina 返回状态、已使用输入、`vid prompt` 路径、最高尝试版本和可选下一步。

## 视频后的发布路由

- 默认自主分支不设发布前确认节点：MP4 通过可解码、竖屏和时长校验并保存到 `OUTPUT/RUN_ID.mp4` 后，记录基础质检信息并直接进入模块 03。
- 用户明确要求“发布前确认”“只生成不发布”“本次不用发布”等暂停发布时，必须在本模块硬停。
- 硬停时展示正式视频、首中尾帧、vid prompt、TNS 记录和是否建议发布；收到用户明确发布授权后进入模块 03。

## 重试

- Dreamina 提交命令必须保持单个 `--image`，且 vid prompt 只引用 `@图1`；不符合该输入合同的视频节点一律弃用。
- 视频 prompt 初稿固定为 `vid-prompt-v1.txt`；`v1` 是首次提交，内容必须由 `prompt_lint.py derive` 从 `grid-prompt.txt` 生成。
- 只有 Dreamina 明确返回 TNS/安全拦截且没有生成可下载 MP4 时，才允许继续写 `vid-prompt-v2.txt` 到 `vid-prompt-v5.txt` 逐步收敛并重提。
- `auto/fast` 在 TNS 收敛期间仍只使用同一张 `MATERIAL/fixed-role/anna.png`；不得因 TNS 换图、增加第二张图、接入其他模式、路线或兜底工具。
- TNS/安全拦截后的每个收敛版本必须重新人工改写，重新运行 `prompt_lint.py`，lint 通过后才可提交 Dreamina。
- 到 `v5` 仍因 TNS/安全拦截未生成 MP4 时，停止，不发布，并报告 `v1-v5` 的失败摘要和最后可选下一步。
- `v2-v5` 收敛仅适用于 TNS/安全拦截；网络、登录、积分、参数错误、上传失败、超时、Dreamina 返回非 TNS 失败等按硬阻断报告。
- 每次 TNS 尝试必须记录版本号、prompt 路径、Dreamina 返回状态、失败原因和是否进入下一版；最终交付时报告最高尝试版本。

## 通过标准

- Dreamina 只收到固定角色图 `MATERIAL/fixed-role/anna.png`；vid prompt 由 `prompt_lint.py derive --mode fast` 生成并通过校验。
- vid prompt 只含 `@图1` 的单图指代语义。
- 下载到的 MP4 可解码、竖屏、约 5-6 秒，并整理为 `OUTPUT/RUN_ID.mp4`。
- 默认自主分支可直接进入模块 03；用户要求确认/不发布时，必须取得用户发布授权后才可进入模块 03。
