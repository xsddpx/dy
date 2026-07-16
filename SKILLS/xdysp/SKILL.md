---
name: xdysp
description: /xdysp、xdysp 或 $xdysp 的只生成视频入口；按 dy 项目的 Anna auto/fast 三图参考短视频流程，使用人物图、衣柜人台商品图和环境图完成选题、prompt、Dreamina 生成、下载、Google Drive 上传和运行记录，不执行内容审查、视频质检或平台发布，由用户亲自检查成片。
---

# xdysp

- 将含 `AGENTS.md` 与 `DOCS/PROJECT.md` 的当前 Git 根目录设为 `PROJECT_ROOT`；找不到时使用 `~/Codex/dy`。
- 读取 `~/.codex/AGENTS.md`、`$PROJECT_ROOT/AGENTS.md` 和 `$PROJECT_ROOT/DOCS/PROJECT.md`，再读取模块 01、02、04；出现环境问题时读取模块 00。模块 03 不属于本技能流程。
- 空调用执行 `anna auto/fast`，其中 `fast` 等同 `auto`；将附加内容作为本次主题、衣柜图编号或模板要求。
- 正式视频固定使用三张参考图：`@图1` 人物、`@图2` 衣柜人台商品图、`@图3` 环境；衣柜图片和服装描述必须来自模块 05 的同一入库条目。
- 按项目协议创建唯一 `RUN_ID` 并建档，执行模块 01 的选题与 prompt 流程，再执行模块 02 的 Dreamina 生成、下载和 Google Drive 上传分支。
- Dreamina 返回成功并下载原始 MP4 后，直接整理为 `OUTPUT/RUN_ID.mp4`；不执行 MP4 技术检查，不抽取首中尾代理帧，不执行人脸、身材、动作、构图或整体观感审查。
- 只要整理出正式视频就按模块 02 上传 Google Drive；上传失败时记录原因和 `needs_retry: true`，继续记录收尾。
- 按模块 04 完成记录与收尾，质检状态写为 `not_performed` 并注明成片由用户自行检查，发布状态写为 `not_requested`。
- 生成完成后展示正式视频、vid prompt、TNS 记录、Drive 上传状态和关键文件路径，然后结束本次流程。
- 本技能不操作抖音、快手或其他发布平台；同一请求即使附带发布字样，也先完成只生成流程并说明发布需另行使用 `/xdy` 明确发起。
- 所有流程与验收以项目文档为准，不在本技能重复 SOP。
