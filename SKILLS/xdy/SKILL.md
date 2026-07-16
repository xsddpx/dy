---
name: xdy
description: /xdy、xdy、$xdy、今天日更、fast 或快速通道入口；执行 dy 项目的 Anna 三图参考短视频主链，支持附带主题、衣柜编号、动作模板、发布前确认或本次不发布要求，默认质检、上传 Google Drive 并同步发布抖音与快手。
---

# xdy

- 将含 `AGENTS.md` 与 `DOCS/PROJECT.md` 的当前 Git 根目录设为 `PROJECT_ROOT`；找不到时使用 `~/Codex/dy`。
- 读取 `~/.codex/AGENTS.md`、`$PROJECT_ROOT/AGENTS.md` 和 `$PROJECT_ROOT/DOCS/PROJECT.md`，再按项目路由读取 `DOCS/PIPELINE/01_RUN_INIT.md` 至 `06_RUN_FINALIZE.md`；环境问题按需读取 `DOCS/RUNBOOKS/ENVIRONMENT_REPAIR.md`。
- 每次正式运行首先执行阶段 01 创建唯一 `RUN_ID` 和 `run/started` 事件，再进入任何选题、素材或生成动作。
- 空调用执行完整 `/xdy` 主链；`fast` 与 `auto` 仅作为兼容调用别名。附加内容作为本次主题、衣柜图编号、动作模板或发布模式要求。
- 默认发布模式在阶段 04 质检并上传 Drive 后进入阶段 05。用户明确要求“本次不发布”时记录 `not_requested` 并直接进入阶段 06；用户明确要求“发布前确认”时记录 `awaiting_confirmation` 并暂停，确认后才进入阶段 05，取消后进入阶段 06。
- 正式视频固定使用三张参考图：`@图1` 人物、`@图2` 衣柜人台商品图、`@图3` 环境；衣柜图片和服装描述必须来自 `DOCS/WORKFLOWS/WARDROBE_INGEST.md` 定义的同一入库条目。
- 不执行 MP4 技术检查；按阶段 04 执行胸部体量内容质检、正式成片整理和 Google Drive `最终视频/` 上传，再按所选发布模式路由。
- 交付按 `AGENTS.md` 只汇报已验证的成片信息、Drive 链接、最终 prompt、生成与 TNS 状态；有 Drive 链接时不展示或链接图片，媒体仅在用户明确要求且不违反项目交付规则时内嵌。
- 所有流程与验收以项目文档为准，不在本技能重复 SOP。
