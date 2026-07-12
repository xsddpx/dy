# 模块 02：Dreamina 视频生成

## 职责

使用模块 01 派生的 vid prompt、固定角色图和固定环境图提交 Dreamina 并下载 MP4。`xdy` 完成胸部体量质检后整理正式成片，`xdysp` 跳过内容质检直接整理正式成片；两条路线只要生成正式成片都上传 Google Drive，再分别进入发布或记录收尾。

## 输入合同与命令

- 固定使用两张图片输入：`MATERIAL/fixed-role/anna.png` 是第一张图，prompt 以 `@图1` 指代；`TEMP/RUN_ID/environment-path.txt` 中锁定的环境图是第二张图，prompt 以 `@图2` 指代。同一次运行的图片路径和顺序固定。
- `TEMP/RUN_ID/vid-prompt-v1.txt` 必须由模块 01 的 `derive --mode fast` 生成并通过校验；内容不合格时回模块 01 重写 `grid-prompt.txt`。
- 图片使用绝对路径提交；`--duration` 按画面节奏选择 `5`、`6` 或 `7`。

```bash
ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"
ENV_IMAGE="$(cat "TEMP/$RUN_ID/environment-path.txt")"
test -f "$ENV_IMAGE"

dreamina multimodal2video \
  --image "$ROOT_DIR/MATERIAL/fixed-role/anna.png" \
  --image "$ENV_IMAGE" \
  --prompt "$(cat "TEMP/$RUN_ID/vid-prompt-v1.txt")" \
  --model_version seedance2.0_vip \
  --ratio 9:16 \
  --video_resolution 720p \
  --duration 5
```

默认跳过模块 00。网络、登录、积分、参数、上传、下载或超时等环境问题转模块 00 做最小修复并复测原失败点。

## 成片整理与胸部体量质检

- `xdy`：从临时 MP4 抽取首段、中段、尾段三张代理图，建议约为 `0.5s`、视频中点和结尾前 `0.5s`；另从固定角色图制作一张代理图。每张均小于 `100KB`，仅用于 Codex 视觉检查。
- `xdy`：执行者亲自逐张打开三帧并与固定角色代理图对照，不能只依赖脚本或平台预览；仅胸部体量明显偏小时阻断，其余全部通过。硬门通过后，将临时 MP4 整理为 `OUTPUT/RUN_ID.mp4`，并记录代理图和人工结论。
- `xdysp`：Dreamina 成功返回并下载原始 MP4 后，直接整理为 `OUTPUT/RUN_ID.mp4`；不抽取代理帧，不执行内容审查或视频质检，运行记录将质检状态写为 `not_performed`，成片由用户本人检查。
- 两条路线的发布、归档和交付始终使用 `OUTPUT/RUN_ID.mp4` 对应的原始 MP4。

## Google Drive 上传与发布路由

- `xdy` 或 `xdysp` 只要整理出 `OUTPUT/RUN_ID.mp4`，就使用已连接的 Google Drive 应用将本次正式原始 MP4 上传到 My Drive 根目录；不转换格式，不从 `TEMP/` 或旧 `OUTPUT/` 推断文件。
- 上传源文件使用 `OUTPUT/RUN_ID.mp4` 的绝对路径，目标文件名固定为 `RUN_ID.mp4`，MIME 类型使用 `video/mp4`；上传参数不传父文件夹 ID，等价于 `parent_folder_id = null`，不创建额外文件夹。
- 上传返回完成后，通过 My Drive 根目录列表或精确文件名搜索核对结果。同一 `RUN_ID`、同一正式成片已记录为上传成功时跳过重复上传；新 `RUN_ID` 或新成片继续上传。
- 在 `TEMP/RUN_ID/RUN_ID-run-record.jsonl` 记录 `google_drive/uploaded` 或 `google_drive/failed`。成功时记录文件名、文件 ID、URL、大小和修改时间等实际可用返回信息；无法取得的字段不虚构。
- 登录、权限、网络、配额、上传或核对失败时记录明确原因和 `needs_retry: true`。`xdy` 继续进入模块 03，`xdysp` 继续进入模块 04；Drive 失败不阻断后续流程。
- `xdy` 中用户明确要求“发布前确认”“只生成不发布”或“本次不用发布”时，Google Drive 自动上传仍执行；完成后在进入模块 03 前硬停，展示正式视频、首中尾帧、vid prompt、TNS 记录、Drive 上传状态和发布建议，取得明确授权后再进入模块 03。
- `xdysp` 完成 Drive 上传尝试后直接进入模块 04，不进入模块 03；最终展示正式视频、vid prompt、TNS 记录、Drive 上传状态和关键文件路径。

## TNS 重试

- `vid-prompt-v1.txt` 是首次提交。仅当 Dreamina 明确返回 TNS/安全拦截且没有可下载 MP4 时，才回模块 01 在固定合同内重选衣柜款式，生成 `vid-prompt-v2.txt` 至 `vid-prompt-v5.txt`。
- 每版重新运行 prompt lint，通过后再提交；固定 `@图1` 角色图、`environment-path.txt` 已锁定的 `@图2` 环境图、双图顺序和本次已选动作模板保持不变。
- 每次记录版本、prompt 路径、Dreamina 状态、失败原因和是否继续。到 `v5` 仍无产物时停止、不发布，并报告完整失败摘要。
