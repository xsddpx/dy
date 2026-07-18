---
name: xdy
description: /xdy、xdy、$xdy、今天日更、fast、auto 或快速通道入口；执行 dy 项目的 Anna 双图参考短视频主链，支持附带主题、衣柜编号、动作模板、发布前确认或本次不发布要求，默认质检、上传 Google Drive 并同步发布抖音与快手。
---

# xdy

- 将含 `AGENTS.md` 与 `DOCS/PROJECT.md` 的当前 Git 根目录设为 `PROJECT_ROOT`；找不到时使用 `~/Codex/dy`。
- 读取全局与项目 `AGENTS.md`、`$PROJECT_ROOT/DOCS/PROJECT.md`，再按顺序读取 `DOCS/MODULES/MAIN_01_RUN_LIFECYCLE.md`、`MAIN_02_CONTENT_PROMPT.md`、`MAIN_03_VIDEO_DELIVERY.md` 和 `MAIN_04_PUBLISH.md`；仅在出现环境问题时读取 `AUX_ENV_REPAIR.md`。
- 每次正式运行先按主链 01 创建唯一 `RUN_ID` 和 `run/started` 事件，再执行主链 02 → 03；主链 03 后按发布模式进入主链 04、直接收尾或等待授权，各分支结束后回主链 01 收尾。
- 空调用执行完整主链；`fast` 与 `auto` 是兼容别名。附加内容作为本次主题、衣柜编号、动作模板、`5`/`6`/`7` 秒时长或发布模式要求；用户指定的有效衣柜、动作和时长优先，其他时长不得提交生成。
- 默认在主链 03 完成内容质检和 Drive 上传尝试后进入主链 04。用户明确要求“本次不发布”时记录 `not_requested` 并直接收尾；用户要求“发布前确认”时记录 `awaiting_confirmation` 并暂停，取得明确授权后才进入主链 04，等待期间明确取消时更新为 `not_requested` 并直接回主链 01 收尾。
- 正式视频固定使用两张参考图：`@图1` 为 Anna 固定角色图，`@图2` 为本次锁定的固定环境图；穿搭事实来自 `MATERIAL/anna-wardrobe.md`。
- 每个 `vN` 提交前必须通过主链 03 的生成合同门禁并保留不可变清单；等待发布确认时不得提前收尾。
- 按主链 03 执行胸部体量内容质检、正式成片整理，并将成片上传到 Google Drive 的 My Drive 根目录；不扩大项目定义的质检范围。
- 交付只汇报已验证的成片信息、Drive 链接、最终 prompt、生成与 TNS 状态。发布前确认只汇报质检结论和相关路径/状态，不内嵌或链接首中尾帧；其他交付仅在用户明确要求且不含 Drive 链接时内嵌媒体。只要交付中附上 Drive 链接，就不再展示、附上或链接任何图片。
- 所有执行细则和验收以项目文档为准，不在本技能重复 SOP。
