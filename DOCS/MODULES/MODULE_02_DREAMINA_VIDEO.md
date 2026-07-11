# 模块 02：Dreamina 视频生成

## 职责

使用模块 01 派生的 vid prompt 和固定角色图提交 Dreamina，下载并检查正式 MP4，完成人脸与身材质检，再按用户要求进入发布或暂停。

## 输入合同与命令

- `MATERIAL/fixed-role/anna.png` 是唯一图片输入，prompt 统一以 `@图1` 指代；不得增加第二张图或切换其他路线。
- `TEMP/RUN_ID/vid-prompt-v1.txt` 必须由模块 01 的 `derive --mode fast` 生成并通过校验；内容不合格时回模块 01 重写 `grid-prompt.txt`。
- 图片使用绝对路径提交；`--duration` 按画面节奏选择 `5`、`6` 或 `7`。

```bash
dreamina multimodal2video \
  --image /Users/Shared/codex/dy/MATERIAL/fixed-role/anna.png \
  --prompt "$(cat TEMP/RUN_ID/vid-prompt-v1.txt)" \
  --model_version seedance2.0_vip \
  --ratio 9:16 \
  --video_resolution 720p \
  --duration 5
```

默认跳过模块 00。网络、登录、积分、参数、上传、下载或超时等环境问题转模块 00 做最小修复并复测原失败点。

## 媒体可用性检查

Dreamina 返回成功后将媒体下载到临时路径并等待下载进程退出，再执行：

```bash
ffprobe -v error -show_entries stream=width,height -show_entries format=duration -of json TEMP/RUN_ID/downloaded.mp4
```

- 记录方向、分辨率和时长；9:16、720p、约 5–7 秒是目标规格，偏差记为 warning。
- 确认文件可完整解码后整理为 `OUTPUT/RUN_ID.mp4`。大小、哈希、播放或解码异常时，按模块 00 的下载传输路径复用原 `submit_id` 取回，不改变任务和 prompt。

## 人脸与身材质检

- 从正式 MP4 抽取首段、中段、尾段三张代理图，建议约为 `0.5s`、视频中点和结尾前 `0.5s`；另从固定角色图制作一张代理图。每张均小于 `100KB`，仅用于 Codex 视觉检查。
- 执行者亲自逐张打开三帧并与固定角色代理图对照，不能只依赖脚本、`ffprobe` 或平台预览。
- 内容发布仅保留两项硬门：人脸身份一致；胸部大小、上身体量、纤细腰线、腰胯比例、臀胯轮廓和整体 S 型身材一致且动作过程中无明显漂移。
- 任一帧未通过硬门时阻断发布，并记录失败帧、问题和下一步。穿搭结构、颜色、动作、场景、构图、贴片、分屏、局部畸形及其他观感差异只记 warning。
- 运行记录写入固定角色代理图、三张视频代理图及两项人工对照结论；正式产物、发布和归档始终使用原始 MP4。

## 发布路由

- MP4 可解码且两项内容硬门通过后，保存到 `OUTPUT/RUN_ID.mp4` 并默认进入模块 03。
- 用户明确要求“发布前确认”“只生成不发布”或“本次不用发布”时在此硬停，展示正式视频、首中尾帧、vid prompt、TNS 记录和发布建议；取得明确授权后再进入模块 03。

## TNS 重试

- `vid-prompt-v1.txt` 是首次提交。仅当 Dreamina 明确返回 TNS/安全拦截且没有可下载 MP4 时，才人工改写 `vid-prompt-v2.txt` 至 `vid-prompt-v5.txt`。
- 每版重新运行 prompt lint，通过后再提交；始终保持同一张固定角色图和单个 `@图1` 输入。
- 每次记录版本、prompt 路径、Dreamina 状态、失败原因和是否继续。到 `v5` 仍无产物时停止、不发布，并报告完整失败摘要。

## 通过标准

- Dreamina 只收到固定角色图和通过校验的单图 vid prompt。
- 正式 MP4 已完成媒体信息记录、完整解码和 `OUTPUT/RUN_ID.mp4` 整理。
- 固定角色代理图与首中尾三帧已经人工对照，人脸身份和身材比例两项硬门通过。
- 默认分支可进入模块 03；用户要求确认或不发布时已按发布路由暂停。
