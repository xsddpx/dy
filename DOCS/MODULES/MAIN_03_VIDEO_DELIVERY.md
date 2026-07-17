# 主链 03：视频生成与交付

## 职责

使用主链 02 派生的 vid prompt、固定角色图和固定环境图提交 Dreamina 并下载 MP4。`xdy` 完成胸部体量质检后整理正式成片，`xdysp` 跳过内容质检直接整理正式成片；两条路线只要生成正式成片都上传 Google Drive，再分别进入发布或运行收尾。

## 输入合同与命令

- 固定使用两张图片输入：`MATERIAL/fixed-role/anna.png` 是第一张图，prompt 以 `@图1` 指代；`TEMP/RUN_ID/environment-path.txt` 中锁定的环境图是第二张图，prompt 以 `@图2` 指代。同一次运行的图片路径和顺序固定。
- `TEMP/RUN_ID/vid-prompt-v1.txt` 必须由主链 02 的 `derive --mode fast` 生成并通过校验；内容不合格时回主链 02 重写 `grid-prompt.txt`。
- 图片使用绝对路径提交。用户明确指定时长时优先使用指定值，但合法值仅为 `5`、`6` 或 `7`；指定其他值时停止并要求改为合法值。未指定时按画面节奏从这三个值中选择。

## 生成前合同门禁

提交 Dreamina 前，必须执行合同命令。命令验证当前 `RUN_ID`、运行记录、环境锁、prompt 机械派生关系、lint、双图绝对路径及顺序、`@图1`/`@图2` 引用、9:16、720p 和 `5`/`6`/`7` 秒时长；通过后首次写入不可变的 `TEMP/RUN_ID/logs/contracts/generation-vN.json`。同版本以相同输入重复执行是幂等操作，输入发生变化时拒绝覆盖旧清单。返回非零时禁止提交 Dreamina，并回到对应主链修正。

```bash
ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"
RUN_ROUTE="${RUN_ROUTE:?xdy 或 xdysp}"
DURATION="${DURATION:?5、6 或 7}"
PROMPT_VERSION="${PROMPT_VERSION:-1}"

.venv/bin/python TOOLS/run_workspace.py contract "$RUN_ID" \
  --phase pre-generation \
  --route "$RUN_ROUTE" \
  --duration "$DURATION" \
  --prompt-version "$PROMPT_VERSION"

ENV_IMAGE="$(cat "TEMP/$RUN_ID/environment-path.txt")"
test -f "$ENV_IMAGE"

dreamina multimodal2video \
  --image "$ROOT_DIR/MATERIAL/fixed-role/anna.png" \
  --image "$ENV_IMAGE" \
  --prompt "$(cat "TEMP/$RUN_ID/vid-prompt-v${PROMPT_VERSION}.txt")" \
  --model_version seedance2.0_vip \
  --ratio 9:16 \
  --video_resolution 720p \
  --duration "$DURATION"
```

紧邻真实提交前写入标准 `dreamina/submit` 事件，其 `data` 必须包含：`version: vN`、`duration`、`ratio: 9:16`、`video_resolution: 720p`、严格有序的两张绝对路径 `reference_images`、本次相对路径 `prompt`，以及清单中的 `prompt_sha256`。生成成功事件的 `status` 写为 `success`，并在 `data.version` 明确记录实际成功的 `vN`；不能用缺省版本或旧运行事件补齐。

默认跳过环境修复辅助流程。网络、登录、积分、参数、上传、下载或超时等环境问题转 `AUX_ENV_REPAIR.md` 做最小修复并复测原失败点。

## 成片整理与胸部体量质检

- `xdy`：从临时 MP4 抽取首段、中段、尾段三张代理图，建议约为 `0.5s`、视频中点和结尾前 `0.5s`；另从固定角色图制作一张代理图。每张均小于 `100KB`，仅用于 Codex 视觉检查。
- `xdy`：执行者亲自逐张打开三帧并与固定角色代理图对照，不能只依赖脚本或平台预览；仅胸部体量明显偏小时阻断，其余全部通过。通过时将临时 MP4 整理为 `OUTPUT/RUN_ID.mp4` 并记录 `quality` 状态 `pass`。阻断时不创建正式 OUTPUT，记录 `quality` 状态 `blocked`、Drive `not_attempted` 和发布 `not_requested`，再以 `quality_failed` 结果进入主链 01 收尾。
- `xdysp`：Dreamina 成功返回并下载原始 MP4 后，直接整理为 `OUTPUT/RUN_ID.mp4`；不抽取代理帧，不执行人脸、身材、动作、构图或整体观感等内容审查，运行记录将质检状态写为 `not_performed`，成片由用户本人检查。收尾合同仍机械验证文件可读、720x1280 和请求时长，这不属于内容质检。
- 正式成片整理完成后写入非 artifact 的 `output/created` 事件，`status` 为 `ready`，`data.output_video` 精确写为 `OUTPUT/RUN_ID.mp4`；后续可追加 artifact 索引，但不能用 artifact 代替正式输出事件。
- 两条路线的发布、归档和交付始终使用 `OUTPUT/RUN_ID.mp4` 对应的原始 MP4。

## Google Drive 上传与发布路由

- `xdy` 或 `xdysp` 只要整理出 `OUTPUT/RUN_ID.mp4`，就使用已连接的 Google Drive 应用将本次正式原始 MP4 上传到 My Drive 根目录；不转换格式，不从 `TEMP/` 或旧 `OUTPUT/` 推断文件。
- 上传源文件使用 `OUTPUT/RUN_ID.mp4` 的绝对路径，目标文件名固定为 `RUN_ID.mp4`，MIME 类型使用 `video/mp4`；上传参数不传父文件夹 ID，等价于 `parent_folder_id = null`，不创建额外文件夹。
- 上传返回完成后，通过 My Drive 根目录列表或精确文件名搜索核对结果。同一 `RUN_ID`、同一正式成片已记录为上传成功时跳过重复上传；新 `RUN_ID` 或新成片继续上传。
- 在 `TEMP/RUN_ID/RUN_ID-run-record.jsonl` 记录 `google_drive/uploaded` 或 `google_drive/failed`。成功时至少记录 `file_name`、`mime_type: video/mp4`、`size`、`file_id` 或 `url`，并在 My Drive 根目录回读核验后记录 `root_verified: true`；连接器返回的 `parent_ids` 可作为回读元数据保留，但不得传入或记录目标子文件夹字段。无法取得的字段不虚构。
- 登录、权限、网络、配额、上传或核对失败时记录明确原因和 `needs_retry: true`。`xdy` 继续进入主链 04，`xdysp` 回主链 01 收尾；Drive 失败不阻断后续流程。
- `xdy` 中用户明确要求“只生成不发布”“本次不发布”或“本次不用发布”时，Google Drive 自动上传仍执行；完成后记录发布状态 `not_requested` 并直接回主链 01 收尾，绝不进入主链 04，也不等待后续发布授权。
- `xdy` 中用户明确要求“发布前确认”时，Google Drive 自动上传仍执行；完成后记录 `awaiting_confirmation` 并在主链 04 前硬停。确认信息只汇报质检结论、正式视频与 vid prompt 的路径、生成与 TNS 状态、Drive 上传状态和当前待发布状态，不内嵌、展示或链接固定角色代理图及首中尾帧；取得明确授权后才进入主链 04，用户明确取消时则更新为 `not_requested` 并直接回主链 01 收尾。
- `xdysp` 完成 Drive 上传尝试后直接回主链 01 收尾，不进入主链 04；最终只汇报已验证的正式成片信息、vid prompt 路径、生成与 TNS 状态、Drive 上传状态和关键文件路径。
- 会话交付一旦附上 Google Drive 链接，同一交付中不再展示、附上或链接任何图片，包括固定角色代理图和首中尾帧。

## TNS 重试

- `vid-prompt-v1.txt` 是首次提交。仅当 Dreamina 明确返回 TNS/安全拦截且没有可下载 MP4 时，才回主链 02 在固定合同内重选衣柜款式，生成 `vid-prompt-v2.txt` 至 `vid-prompt-v5.txt`。
- 每版重新运行 prompt lint，通过后再提交；固定 `@图1` 角色图、`environment-path.txt` 已锁定的 `@图2` 环境图、双图顺序和本次已选动作模板保持不变。
- 每次记录版本、prompt 路径、Dreamina 状态、失败原因和是否继续。到 `v5` 仍无产物时写入 `dreamina/failed`，状态为 `failed` 或 `blocked`，并明确记录 `data.version: v5` 与 `data.reason_category: tns`；同时记录质检 `not_performed`、Drive `not_attempted`、发布 `not_requested`，再以 `generation_failed` 结果进入主链 01 收尾。
