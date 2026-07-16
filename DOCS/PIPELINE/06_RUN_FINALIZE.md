# 阶段 06：运行记录与收尾

## 职责

汇总阶段 01–05 已追加的事件，补齐本次路线的终态，刷新 `RUN_ID-run-record.md`，并执行正式命名审计。本阶段不重新生成、不重新上传、不重新发布，也不从旧运行目录补猜状态。

## 必须保留的记录

### 运行与素材

- 本次 `RUN_ID`、入口来源和 `run/started` 首条事件。
- 完整衣柜编号 `衣柜图-季节-NNN`、季节和季内三位编号。
- 衣柜图片路径、服装描述路径、固定人物图和固定环境图路径。
- 三张输入的固定顺序与 SHA-256。
- 所选动作模板。
- 旧纯数字衣柜编号只通过 `MATERIAL/wardrobe-id-migration.json` 读取兼容，不回写旧运行记录。

### Prompt 与 Dreamina

- 每一份 `vid-prompt-vN.txt` 的路径和 lint 结果。
- 每个版本对应的 Dreamina 提交日志、`submit_id`、查询状态链、终态、原始失败原因和下载路径。
- TNS 是否触发、下一版本以及最终成功版本；重试到 `v5` 时保留完整版本链。
- 全部版本中的衣柜编号、三张图片路径、顺序、哈希、服装事实和动作模板保持不变。

### 成片、质检与 Drive

- 阶段 03 的原始下载路径和正式 `OUTPUT/RUN_ID.mp4` 路径。
- `xdy`：固定角色代理图、首中尾视频代理图、人工对照方式，以及胸部体量是否明显偏小的结论。
- `xdysp`：内容质检状态为 `not_performed`，并注明由用户本人检查。
- Google Drive `最终视频/` 上传状态。
- Drive 成功时记录实际取得的文件夹 ID、文件名、文件 ID、URL、大小和修改时间；失败时记录原因和 `needs_retry`。

### 发布

- 抖音、快手各自状态及报告路径。
- `publish-both-report.json` 的路径和聚合结论。
- 未进入阶段 05 时，发布状态必须明确记录为 `not_requested`，不能写成失败。
- `awaiting_confirmation` 只表示等待用户选择，不能伪装成 `not_requested` 或已完成。

## 等待确认不是收尾

阶段 04 写入 `awaiting_confirmation` 时，可以刷新 Markdown 摘要供用户确认，但不得追加 `run/completed` 终态：

```bash
.venv/bin/python TOOLS/run_record.py summary \
  "TEMP/$RUN_ID/$RUN_ID-run-record.jsonl" \
  --md "TEMP/$RUN_ID/$RUN_ID-run-record.md"
```

用户明确同意后进入阶段 05；用户明确取消后把发布状态更新为 `not_requested`，再继续本阶段终态收尾。

## 终态规则

| 结果 | 运行终态 |
|---|---|
| `xdysp` 已生成正式成片并完成 Drive 尝试 | `success`；发布为 `not_requested` |
| `xdy` 明确不发布，已生成正式成片并完成 Drive 尝试 | `success`；发布为 `not_requested` |
| `xdy` 双平台均成功 | `success`；发布为 `published` |
| `xdy` 只有一个平台成功 | `partial`；分别保留成功与失败平台状态 |
| `xdy` 两个平台均失败 | `failed`；正式成片与 Drive 状态仍保留 |
| Dreamina 到 `v5` 仍无产物，或 `xdy` 内容硬门失败 | `failed`；不得虚构正式成片或发布状态 |
| Drive 上传失败但生成及所选发布路线完成 | 不改变主路线终态；另记 `needs_retry: true` |

终态事件应写清 `run_id`、路线、正式视频路径（若存在）、最终 prompt 版本、Dreamina 结论、质检结论、Drive 状态、抖音状态、快手状态和整体结果。使用 `TOOLS/run_record.py append` 追加 `stage=run` 的最终事件：`success` 或 `partial` 使用 `event=completed`，生成或质检失败使用 `event=failed`；状态必须与上表一致。

## 刷新摘要与命名审计

终态事件写入后刷新 Markdown：

```bash
.venv/bin/python TOOLS/run_record.py summary \
  "TEMP/$RUN_ID/$RUN_ID-run-record.jsonl" \
  --md "TEMP/$RUN_ID/$RUN_ID-run-record.md"
```

摘要至少包含：

- 成片信息和正式视频路径。
- Google Drive 上传状态及可用链接。
- 最终 `vid-prompt-vN.txt` 路径。
- Dreamina 生成终态和 TNS 版本链。
- `xdy` 质检结论，或 `xdysp` 的 `not_performed`。
- 发布状态；尝试发布时包含平台报告与聚合报告路径。

最后执行命名审计：

```bash
.venv/bin/python TOOLS/run_workspace.py audit
```

审计检查正式运行目录、运行记录与 `OUTPUT/*.mp4` 的命名和对应关系；候选、调试、缓存、`TEMP/del/` 及其他辅助目录不作为正式 RUN_ID。必须保留时间戳式目录名的历史辅助目录，应在目录根部放置 `.run-workspace-auxiliary` 明确标记，不得依赖审计静默忽略。审计失败时先修复记录或命名关系，再完成会话交付。
