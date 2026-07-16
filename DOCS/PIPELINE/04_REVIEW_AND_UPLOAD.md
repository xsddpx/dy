# 阶段 04：质检、正式成片与 Google Drive 上传

## 职责

接收阶段 03 已下载并记录的原始 MP4，按入口分支处理：

- `xdy`：执行固定角色与首中尾三帧人工视觉对照，通过内容硬门后整理正式成片。
- `xdysp`：不抽代理帧，不执行内容审查或视频质检，直接整理正式成片，由用户本人检查。

两条路线只要得到 `OUTPUT/RUN_ID.mp4`，都必须尝试上传 Google Drive 的 `最终视频/`，再根据发布意图进入阶段 05 或阶段 06。

## 通用输入合同

- 只使用阶段 03 成功事件中记录的确切下载路径，不从 `TEMP/`、Dreamina 历史任务或旧 `OUTPUT/` 猜测成片。
- 当前成功版本必须具备 prompt、`submit_id`、查询终态和本地下载记录。
- 下载文件必须存在且非空；本项目不执行 MP4 编码、画幅、时长或其他技术质检。

```bash
# 使用阶段 03 成功事件中记录的实际路径：
DOWNLOADED_MP4="TEMP/$RUN_ID/downloads/vN/SUBMIT_ID_video_1.mp4"

test -s "$DOWNLOADED_MP4"
```

文件缺失、损坏或下载不完整时返回阶段 03，复用原 `submit_id` 重新查询或下载；不重新提交生成任务。

## `xdy` 内容质检

1. 从临时 MP4 抽取首段、中段、尾段三帧，建议时间点约为 `0.5s`、视频中点和结尾前 `0.5s`。
2. 从 `MATERIAL/fixed-role/anna.png` 制作固定角色代理图。
3. 代理图写入 `TEMP/RUN_ID/proxies/`，每张小于 `100KB`，只用于 Codex 视觉检查。
4. 执行者亲自逐张打开首、中、尾三帧，并与固定角色代理图对照；不能只依赖脚本、文件元数据或平台缩略图。
5. 唯一内容硬门是胸部体量是否明显偏小：明显偏小则阻断，其余情况全部通过。
6. 在 JSONL 中记录固定角色代理图、三帧代理图、人工检查方式、`bust_volume_obviously_smaller` 和最终结论。

检查不通过时保留阶段 03 的原始下载及完整记录，不创建 `OUTPUT/RUN_ID.mp4`，直接进入阶段 06 失败收尾。

## `xdysp` 跳过质检分支

- 不抽取固定角色或视频代理图。
- 不执行内容审查、人物对照或胸部体量判断。
- JSONL 中将内容质检状态记录为 `not_performed`，并注明 `review_owner=user`。
- 确认阶段 03 记录的下载文件存在且非空后，即可整理正式成片。

## 整理正式成片

仅在 `xdy` 内容硬门通过或当前入口为 `xdysp` 时，将本次确切下载文件复制为固定输出：

```bash
cp "$DOWNLOADED_MP4" "OUTPUT/$RUN_ID.mp4"
test -s "OUTPUT/$RUN_ID.mp4"
```

发布、归档、上传和交付始终使用 `OUTPUT/RUN_ID.mp4` 对应的原始 MP4，不转码、不降质，也不以代理图代替。

在 JSONL 中记录正式成片路径、来源下载路径、成功 prompt 版本、`submit_id`、文件大小和实际媒体信息，并把 `OUTPUT/RUN_ID.mp4` 登记为保留产物。

## Google Drive 上传

- 使用已连接的 Google Drive 应用，将本次正式原始 MP4 上传到 My Drive 根目录下固定文件夹 `最终视频/`。
- 上传前列出 My Drive 根目录，按完整文件夹名精确匹配未删除的 `最终视频`：
  - 没有同名文件夹时，在根目录创建。
  - 只有一个时，使用其实际文件夹 ID。
  - 存在多个同名文件夹时，停止 Drive 写入并记录重复冲突；不得自行选择或再创建。
- 上传源文件使用 `OUTPUT/RUN_ID.mp4` 的绝对路径，目标文件名固定为 `RUN_ID.mp4`，MIME 类型为 `video/mp4`，`parent_folder_id` 固定传入已确认的 `最终视频` 文件夹 ID。
- 上传完成后，通过 `最终视频/` 文件夹列表或带父文件夹约束的精确文件名搜索核对结果。
- 同一 `RUN_ID`、同一正式成片已经记录为上传成功时跳过重复上传；新 `RUN_ID` 或成片发生变化时继续上传。
- 成功时记录 `google_drive/uploaded`，以及实际取得的文件夹 ID、文件名、文件 ID、URL、大小和修改时间；无法取得的字段不虚构。
- 文件夹发现或创建、登录、权限、网络、配额、上传或核对失败时记录 `google_drive/failed`、明确原因和 `needs_retry: true`。

Drive 上传失败不回滚正式成片，也不阻断 `xdy` 继续发布；`xdysp` 仍进入阶段 06。

## 发布意图与路由

生成意图和确认意图必须分开记录，不再把所有“只生成”表述都视为等待确认：

| 入口或用户意图 | 内容质检 | 发布状态 | 下一步 |
|---|---|---|---|
| `xdy`，未要求暂停或不发布 | 执行 | 准备发布 | 阶段 05 |
| `xdy`，明确要求“发布前确认” | 执行 | `awaiting_confirmation` | 暂停；明确同意后进入阶段 05 |
| `xdy`，明确要求“不发布”或“只生成不发布” | 执行 | `not_requested` | 阶段 06 |
| `xdysp` | `not_performed` | `not_requested` | 阶段 06 |

`awaiting_confirmation` 是运行中的暂停状态，不是终态。等待期间刷新阶段 06 摘要，但不追加 `run/completed`：

- 用户明确同意发布：进入阶段 05。
- 用户明确取消发布：把发布状态改为 `not_requested`，进入阶段 06。

进入确认暂停前，只汇报成片信息、Drive 链接、最终 `vid-prompt-vN.txt`、TNS 版本链、Drive 状态和发布建议。首中尾代理帧仅保留在本次运行目录供执行者质检，不默认交付；附有 Drive 链接时不再展示或链接图片。`xdysp` 不生成首中尾帧，完成 Drive 尝试后直接进入阶段 06。

环境或连接器问题转到 [`../RUNBOOKS/ENVIRONMENT_REPAIR.md`](../RUNBOOKS/ENVIRONMENT_REPAIR.md)，修复后返回本阶段原失败点。
