# 主链 04：双平台发布

## 固定发布合同

`TOOLS/publish_adapter.py both` 固定先抖音、后快手；单平台失败继续另一平台，已发布平台不重复点击。两端只允许 Playwright CDP 直传，不设置位置，不提供 `auto/dialog/current-tab`、AppleScript 文件选择器或 AI 智能封面路径。

- 抖音封面固定使用视频中间帧。
- 抖音从最多 8 个候选标签依次寻找完整匹配，直到应用 4 个或候选耗尽；报告分别保存 `requested_tags` 与 `applied_tags`，不把话题粘连进简介作为降级。
- 两个平台实际应用标签均不得超过 4 个。快手可接收更大的候选池，但只把去重后的前 4 个写入文案，并分别记录 requested 与 applied。
- 快手使用常规视频入口；VR360° 模式、上传或转码未完成均阻断。
- 两个平台点击发布前都必须设置“内容由AI生成”。验证码、登录、安全验证、声明失败和未知错误不自动重试。
- 仅明确分类为导航超时允许自动重试一次；重试前先读平台报告，若已 `published` 则跳过。

## 记录分工

平台 helper 只写各自详细 JSON/Markdown 报告；不写运行 JSONL。聚合适配器生成 `publish-both-report`，统一入口只把两端紧凑结果写成 schema v2 `platform_result` 和 `both_publish` 事件。页面全文、进程列表和重复 DOM 文本只留在 `logs/publish/`。

双端均为 `published` 时聚合终态为 `published`；任一端未成功则为 `blocked`。两者都是真实可收尾状态，但只有前者可形成 `run/completed=success`；后者必须形成 `run/completed=failed`、`outcome=publish_failed`。

## 发布路线

- 默认 `xdy`：Drive 尝试后自动发布。
- `not_requested`：Drive 尝试后记录不发布并收尾。
- `awaiting_confirmation`：Drive 尝试后硬停；只有 `resume --authorize-publish` 才进入发布，`resume --cancel-publish` 改记不发布并收尾。
- `xdysp`：固定不发布。
