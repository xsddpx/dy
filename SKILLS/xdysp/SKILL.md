---
name: xdysp
description: /xdysp、xdysp 或 $xdysp 的裸生成视频入口；按 dy 项目 Anna 双图参考流程完成建档、选题、prompt、Dreamina 生成下载、正式成片整理、Google Drive 上传和运行记录，不执行内容质检或平台发布，由用户亲自检查成片。
---

# xdysp

- 将含 `AGENTS.md` 与 `DOCS/PROJECT.md` 的当前 Git 根目录设为 `PROJECT_ROOT`；找不到时使用 `~/Codex/dy`。
- 读取全局与项目 `AGENTS.md`、`$PROJECT_ROOT/DOCS/PROJECT.md`，再按顺序读取 `DOCS/MODULES/MAIN_01_RUN_LIFECYCLE.md`、`MAIN_02_CONTENT_PROMPT.md` 和 `MAIN_03_VIDEO_DELIVERY.md`；仅在出现环境问题时读取 `AUX_ENV_REPAIR.md`。
- 每次正式运行先按主链 01 创建唯一 `RUN_ID` 和 `run/started` 事件，再执行主链 02 → 主链 03 的 `xdysp` 分支，最后回主链 01 收尾。
- 空调用执行裸生成路线；附加内容作为本次主题、衣柜编号、动作模板或 `5`/`6`/`7` 秒时长要求。用户指定的有效衣柜、动作和时长优先；时长只能从这三个值中选择，其他值不得提交生成。
- 正式视频固定使用两张参考图：`@图1` 为 Anna 固定角色图，`@图2` 为本次锁定的固定环境图；穿搭事实来自 `MATERIAL/anna-wardrobe.md`。
- 每个 `vN` 提交前必须通过主链 03 的生成合同门禁并保留不可变清单。
- Dreamina 成功并下载原始 MP4 后，直接整理为 `OUTPUT/RUN_ID.mp4`；整理时只机械核验文件可读、分辨率和请求时长，不抽取代理帧，不执行人脸、身材、动作、构图或整体观感审查。
- 只要整理出正式视频就尝试上传到 Google Drive 的 My Drive 根目录；上传失败时记录原因和 `needs_retry: true` 并继续收尾。质检状态固定为 `not_performed`，发布状态固定为 `not_requested`。
- 不进入主链 04，不操作抖音、快手或其他发布平台；即使请求附带发布字样，也先完成裸生成路线，并说明发布需另行使用 `/xdy` 发起。
- 交付只汇报已验证的成片信息、Drive 链接、最终 prompt、生成与 TNS 状态；仅在用户明确要求且不含 Drive 链接时内嵌媒体。只要交付中附上 Drive 链接，就不再展示、附上或链接任何图片。
- 所有执行细则和验收以项目文档为准，不在本技能重复 SOP。
