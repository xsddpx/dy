# 主链 01：运行生命周期

## 职责

`TOOLS/xdy_flow.py` 是 schema v2 新运行的唯一写入口，负责 RUN_ID、严格状态迁移、幂等续跑、摘要和原子收尾。121 份旧记录只读兼容，不迁移、不重写，也不能用新入口续跑。

每条 schema v2 事件固定包含 `schema_version、seq、run_id、created_at(+08:00)、stage、event、status、data`。事件名和状态使用枚举；artifact 不参与阶段终态计算。详细证据写入 `TEMP/RUN_ID/logs/`，典型 JSONL 控制在 10KB 内。

## 统一命令

```bash
# 新运行；xdysp 使用 --route xdysp
.venv/bin/python TOOLS/xdy_flow.py run --route xdy

# 查询唯一下一动作
.venv/bin/python TOOLS/xdy_flow.py status "$RUN_ID"

# 从合法断点续跑；不会重复提交、上传或发布
.venv/bin/python TOOLS/xdy_flow.py resume "$RUN_ID"

# 发布前确认路线的授权或取消
.venv/bin/python TOOLS/xdy_flow.py resume "$RUN_ID" --authorize-publish
.venv/bin/python TOOLS/xdy_flow.py resume "$RUN_ID" --cancel-publish
```

`run` 原子创建 `TEMP/RUN_ID/`、`logs/`、首条 `run/started`，锁定本次内容并执行到首个人工或连接器断点。RUN_ID 格式与正式输出仍为 `YYYYMMDD-HHMMSS[-NN]` 和 `OUTPUT/RUN_ID.mp4`。

## 合法断点与恢复

`status` 总是返回当前阶段、是否终态和唯一 `next_action`。`resume` 复用既有 prompt 清单、`submit_id`、正式输出、Drive 终态和已发布平台；进程中断后从最后一个持久事件或 Dreamina 原始提交日志恢复。环境错误保留为可恢复状态，附结构化 doctor 结果，不消耗积分盲目重提。

## 原子收尾

```bash
.venv/bin/python TOOLS/xdy_flow.py complete "$RUN_ID"
```

`complete` 原子追加唯一 `run/completed` 并刷新 Markdown/JSON 摘要。重复调用不产生第二条 completed。等待发布确认时不能收尾。

双平台均为 `published` 才能以 `success` 收尾；任一平台失败时以 `failed`、`outcome=publish_failed` 收尾。状态与聚合报告不一致时拒绝追加 `run/completed`。
