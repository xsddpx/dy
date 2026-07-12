# 模块 02：Dreamina 视频生成

## 职责

使用模块 01 派生的 vid prompt、固定角色图和固定环境图提交 Dreamina，下载正式 MP4，完成胸部体量质检，再按用户要求进入发布或暂停。

## 输入合同与命令

- 固定使用两张图片输入：`MATERIAL/fixed-role/anna.png` 是第一张图，prompt 以 `@图1` 指代；`MATERIAL/fixed-environment/anna-room.png` 是第二张图，prompt 以 `@图2` 指代。图片路径和顺序均固定。
- `TEMP/RUN_ID/vid-prompt-v1.txt` 必须由模块 01 的 `derive --mode fast` 生成并通过校验；内容不合格时回模块 01 重写 `grid-prompt.txt`。
- 图片使用绝对路径提交；`--duration` 按画面节奏选择 `5`、`6` 或 `7`。

```bash
ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

dreamina multimodal2video \
  --image "$ROOT_DIR/MATERIAL/fixed-role/anna.png" \
  --image "$ROOT_DIR/MATERIAL/fixed-environment/anna-room.png" \
  --prompt "$(cat TEMP/RUN_ID/vid-prompt-v1.txt)" \
  --model_version seedance2.0_vip \
  --ratio 9:16 \
  --video_resolution 720p \
  --duration 5
```

默认跳过模块 00。网络、登录、积分、参数、上传、下载或超时等环境问题转模块 00 做最小修复并复测原失败点。

## 胸部体量质检

- 从临时 MP4 抽取首段、中段、尾段三张代理图，建议约为 `0.5s`、视频中点和结尾前 `0.5s`；另从固定角色图制作一张代理图。每张均小于 `100KB`，仅用于 Codex 视觉检查。
- 执行者亲自逐张打开三帧并与固定角色代理图对照，不能只依赖脚本或平台预览。
- 仅胸部体量明显偏小时阻断，其余全部通过。
- 胸部体量硬门通过后，将临时 MP4 整理为 `OUTPUT/RUN_ID.mp4`；运行记录写入固定角色代理图、三张视频代理图和人工结论，发布与归档始终使用原始 MP4。

## Google Drive 上传与发布路由

- 胸部体量硬门通过并整理出 `OUTPUT/RUN_ID.mp4` 后，使用已连接的 Google Drive 应用将本次正式原始 MP4 上传到 My Drive 根目录；不转换格式，不从 `TEMP/` 或旧 `OUTPUT/` 推断文件。
- 上传源文件使用 `OUTPUT/RUN_ID.mp4` 的绝对路径，目标文件名固定为 `RUN_ID.mp4`，MIME 类型使用 `video/mp4`；上传参数不传父文件夹 ID，等价于 `parent_folder_id = null`，不创建额外文件夹。
- 上传返回完成后，通过 My Drive 根目录列表或精确文件名搜索核对结果。同一 `RUN_ID`、同一正式成片已记录为上传成功时跳过重复上传；新 `RUN_ID` 或新成片继续上传。
- 在 `TEMP/RUN_ID/RUN_ID-run-record.jsonl` 记录 `google_drive/uploaded` 或 `google_drive/failed`。成功时记录文件名、文件 ID、URL、大小和修改时间等实际可用返回信息；无法取得的字段不虚构。
- 登录、权限、网络、配额、上传或核对失败时记录明确原因和 `needs_retry: true`，继续进入模块 03，不把 Drive 失败作为抖音或快手发布阻断项。
- 用户明确要求“发布前确认”“只生成不发布”或“本次不用发布”时，Google Drive 自动上传仍执行；完成后在进入模块 03 前硬停，展示正式视频、首中尾帧、vid prompt、TNS 记录、Drive 上传状态和发布建议，取得明确授权后再进入模块 03。

## TNS 重试

- `vid-prompt-v1.txt` 是首次提交。仅当 Dreamina 明确返回 TNS/安全拦截且没有可下载 MP4 时，才回模块 01 在固定合同内重选衣柜款式，生成 `vid-prompt-v2.txt` 至 `vid-prompt-v5.txt`。
- 每版重新运行 prompt lint，通过后再提交；固定 `@图1` 角色图、`@图2` 环境图、双图顺序和动作模板 01 保持不变。
- 每次记录版本、prompt 路径、Dreamina 状态、失败原因和是否继续。到 `v5` 仍无产物时停止、不发布，并报告完整失败摘要。
