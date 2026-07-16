---
name: xdysp
description: /xdysp、xdysp 或 $xdysp 的裸生成视频入口；按 dy 项目三图参考流程完成建档、选题、prompt、Dreamina 生成下载、正式成片整理、Google Drive 上传和运行记录，不执行内容质检或平台发布，由用户亲自检查成片。
---

# xdysp

- 将含 `AGENTS.md` 与 `DOCS/PROJECT.md` 的当前 Git 根目录设为 `PROJECT_ROOT`；找不到时使用 `~/Codex/dy`。
- 读取 `~/.codex/AGENTS.md`、`$PROJECT_ROOT/AGENTS.md` 和 `$PROJECT_ROOT/DOCS/PROJECT.md`，再依次读取 `DOCS/PIPELINE/01_RUN_INIT.md`、`02_CONTENT_AND_PROMPT.md`、`03_VIDEO_GENERATION.md`、`04_REVIEW_AND_UPLOAD.md` 和 `06_RUN_FINALIZE.md`；环境问题按需读取 `DOCS/RUNBOOKS/ENVIRONMENT_REPAIR.md`。
- 每次正式运行首先执行阶段 01 创建唯一 `RUN_ID` 和 `run/started` 事件，再进入阶段 02。
- 空调用执行 `/xdysp` 裸生成路线；附加内容作为本次主题、衣柜图编号或动作模板要求。
- 正式视频固定使用三张参考图：`@图1` 人物、`@图2` 衣柜人台商品图、`@图3` 环境；衣柜图片和服装描述必须来自 `DOCS/WORKFLOWS/WARDROBE_INGEST.md` 定义的同一入库条目。
- Dreamina 成功并下载原始 MP4 后，阶段 04 直接整理为 `OUTPUT/RUN_ID.mp4`；不执行 MP4 技术检查，不抽取代理帧，不执行人脸、身材、动作、构图或整体观感审查。
- 只要整理出正式视频就尝试上传 Google Drive；上传失败时记录原因和 `needs_retry: true`，继续阶段 06。质检状态固定为 `not_performed`，发布状态固定为 `not_requested`。
- 本技能不进入阶段 05，不操作抖音、快手或其他发布平台；同一请求即使附带发布字样，也先完成裸生成路线并说明发布需另行使用 `/xdy` 明确发起。
- 交付按 `AGENTS.md` 报告成片信息、最终 vid prompt、TNS 链和 Drive 状态；有 Drive 链接时不展示或链接图片，不默认内嵌正式视频或代理帧。
- 所有流程与验收以项目文档为准，不在本技能重复 SOP。
