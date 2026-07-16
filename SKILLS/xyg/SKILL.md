---
name: xyg
description: /xyg、xyg 或 $xyg 的 dy 项目衣柜人台商品图生成与入库入口；当用户本次提供服装参考图，并要求生成人台商品图、创建衣柜图或加入项目衣柜时使用。
---

# xyg

- 将含 `AGENTS.md` 与 `DOCS/PROJECT.md` 的当前 Git 根目录设为 `PROJECT_ROOT`；找不到时使用 `~/Codex/dy`。
- 读取 `~/.codex/AGENTS.md`、`$PROJECT_ROOT/AGENTS.md`、`$PROJECT_ROOT/DOCS/PROJECT.md` 和 `$PROJECT_ROOT/DOCS/MODULES/MODULE_05_WARDROBE_IMAGE_ASSETS.md`；仅在出现环境问题时读取模块 00。
- 严格按模块 05 调用 `$imagegen`，完成生成、质检、描述、原子入库与交付；模块文档是唯一执行依据，不在本技能重复 SOP。
- 不触发 `xdy`、`xdysp`、视频生成、Drive 上传或平台发布。
