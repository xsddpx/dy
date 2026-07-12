# 模块 05：Google Drive 自动上传

## 职责与前置条件

将本次正式视频 `OUTPUT/RUN_ID.mp4` 自动上传到 Google Drive 的 My Drive 根目录，并记录结果。

- 模块 02 已通过：正式 MP4 已整理完成，胸部体量唯一内容硬门通过。
- 只上传本次 `RUN_ID` 对应的正式成片，不从 `TEMP/` 或旧 `OUTPUT/` 中推断文件。
- 使用已连接的 Google Drive 应用执行原始 MP4 上传，不转换文件格式。

## 执行要求

- 调用 Google Drive 的文件上传能力，源文件使用 `OUTPUT/RUN_ID.mp4` 的绝对路径。
- 目标文件名固定为 `RUN_ID.mp4`，MIME 类型使用 `video/mp4`。
- 目标为 My Drive 根目录：上传参数不传父文件夹 ID，等价于 `parent_folder_id = null`；不创建额外文件夹。
- 上传返回完成后，通过 My Drive 根目录列表或精确文件名搜索核对结果。
- 同一 `RUN_ID`、同一正式成片已经记录为上传成功时跳过重复上传；新 `RUN_ID` 或新成片继续上传。

## 记录与失败处理

- 在 `TEMP/RUN_ID/RUN_ID-run-record.jsonl` 记录 `google_drive/uploaded` 或 `google_drive/failed`。
- 成功时记录文件名、文件 ID、URL、大小和修改时间等实际可用返回信息；无法取得某字段时不虚构。
- 登录、权限、网络、配额、上传或核对失败时记录明确原因和 `needs_retry: true`，继续进入模块 03，不把 Drive 失败作为抖音或快手发布阻断项。
- 用户要求只生成、不发布或发布前确认时，Google Drive 自动上传仍执行；完成后再停在平台发布确认节点。
