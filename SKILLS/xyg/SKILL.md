---
name: xyg
description: /xyg、xyg 或 $xyg 的 dy 项目衣柜人台商品图生成、入库与 Google Drive 上传入口；当用户本次提供服装参考图并要求创建衣柜图，或明确指定历史衣柜文档做批量图片化迁移时使用。
---

# xyg

- 将含 `AGENTS.md` 与 `DOCS/PROJECT.md` 的当前 Git 根目录设为 `PROJECT_ROOT`；找不到时使用 `~/Codex/dy`。
- 读取 `~/.codex/AGENTS.md`、`$PROJECT_ROOT/AGENTS.md`、`$PROJECT_ROOT/DOCS/PROJECT.md` 和 `$PROJECT_ROOT/DOCS/WORKFLOWS/WARDROBE_INGEST.md`；仅在出现环境问题时读取 `DOCS/RUNBOOKS/ENVIRONMENT_REPAIR.md`。
- 严格按衣柜入库工作流调用 `$imagegen` 和已连接的 Google Drive 应用，完成单图或历史文档批量生成、质检、描述、原子入库、Drive 上传与交付；工作流文档是唯一执行依据，不在本技能重复 SOP。
- Drive 上传成功时只交付回读确认的链接，不再展示或链接图片；无 Drive 链接时按 `AGENTS.md` 和用户明确要求决定是否交付本地正式图。
- 不触发 `/xdy`、`/xdysp`、视频生成或平台发布。
