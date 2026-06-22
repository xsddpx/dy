# 模块 02：参考反推与 prompt

## 职责

- 实际查看 `reference-grid.jpg` 或 `frame-*.png`。
- 写出可见画面、动作、镜头、场景、穿搭、身材可见表达和画面质感。
- 为 `auto` 视频生成准备以确认图为锚点的正式 prompt。

## 规则

- 只支持 `anna auto`。
- 正式视频 Dreamina prompt 只允许 `@图1`，含义为模块 03 自动选中的 Dreamina 原始确认图。
- 不写模型参数、分辨率、结果数、流程说明或合规说明。
- 不写 `direct`、`manual`、`duo`、`swen`、TapNow。
- 默认非 TNS 不运行 `prompt_lint.py`；TNS/安全拦截后的收敛版本必须 lint 通过。

## 通过标准

- 已完成参考类型、姿态、镜头、场景、穿搭、身材描述、动作锁定。
- prompt 与参考宫格动作和选中确认图画面不冲突。
- Dreamina 转写后只包含 `@图1`。
