# 阶段 01：运行建档

## 职责

本阶段是视频主链的固定第一步，负责在任何选题、素材锁定、prompt 编写或生成操作之前创建本次 `RUN_ID`、正式运行目录和运行记录。`xdy` 与 `xdysp` 均从本阶段开始。

本阶段只创建运行身份和首条事件；选题与 prompt 进入阶段 02，完整记录与终态收尾进入阶段 06。

## 范围边界

- `/xyg` 衣柜入库是独立路线，执行 [`../WORKFLOWS/WARDROBE_INGEST.md`](../WORKFLOWS/WARDROBE_INGEST.md)，不进入视频阶段 01–06。
- 评论查看与回复执行 [`../WORKFLOWS/COMMENT_TRIAGE_AND_REPLY.md`](../WORKFLOWS/COMMENT_TRIAGE_AND_REPLY.md)，不进入视频阶段 01–06。
- 环境故障执行 [`../RUNBOOKS/ENVIRONMENT_REPAIR.md`](../RUNBOOKS/ENVIRONMENT_REPAIR.md)，修复后返回视频主链原失败点。

## 启动命令

所有命令从 Git 仓库根目录执行：

```bash
RUN_SOURCE="${RUN_SOURCE:-manual}"
RUN_ID="$(.venv/bin/python TOOLS/run_workspace.py init \
  --source "$RUN_SOURCE" \
  --format id)"
```

`RUN_SOURCE` 应写明本次入口，例如 `automation:xdy`、`automation:xdysp`、`scheduled:0600` 或 `manual`。需要补充模式、主题、定时任务、补跑或 Codex thread 标识时，通过 `init --data` 写入首条事件，不把这些信息拼进 `RUN_ID`。

## 建档合同

- `RUN_ID` 唯一合法格式为 `YYYYMMDD-HHMMSS`；同一秒内首个运行使用纯时间，后续依次追加 `-01` 至 `-99`。
- `init` 按 `Asia/Shanghai` 时间原子创建 `TEMP/RUN_ID/logs/`，确保 `OUTPUT/` 存在，并创建 `TEMP/RUN_ID/RUN_ID-run-record.jsonl`。
- JSONL 的第一条事件必须是 `stage=run`、`event=started`；在这条事件存在前，不得选择衣柜、环境、动作模板或写入 prompt。
- 后续 prompt、素材锁定、Dreamina 日志、下载、代理图、发布报告和运行记录全部写入本次 `TEMP/RUN_ID/`。
- 正式成片固定为 `OUTPUT/RUN_ID.mp4`，其 RUN_ID 必须与运行目录和记录文件完全一致。
- `TEMP/` 是可清理的过程目录，不作为下次运行的默认续跑状态；新任务不得从旧目录推断本次状态。

## 通过标准与路由

同时满足以下条件才进入阶段 02：

1. 命令返回合法且唯一的 `RUN_ID`。
2. `TEMP/RUN_ID/` 与 `TEMP/RUN_ID/RUN_ID-run-record.jsonl` 已存在。
3. 首条记录是本次 `run/started` 事件。

环境、权限、依赖或文件写入失败时，转到 [`../RUNBOOKS/ENVIRONMENT_REPAIR.md`](../RUNBOOKS/ENVIRONMENT_REPAIR.md) 做最小修复，随后重新执行本阶段失败点。
