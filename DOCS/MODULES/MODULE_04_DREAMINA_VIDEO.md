# 模块 04：Dreamina 视频生成

## 职责

- 将 vid prompt 转写为 `@图1=选中确认图`。
- 用 `generation_gate.py` 检查 Dreamina 视频提交前硬门。
- 提交 Dreamina `multimodal2video` 并下载正式 MP4。

## prompt 边界

- img prompt 和 vid prompt 是两个阶段的输入。
- img prompt 用于确认图阶段，使用 `@图1=角色上传图`、`@图2=强遮挡参考图`。
- vid prompt 用于视频阶段，只上传模块 03 选中的 Dreamina 原始确认图，并在 prompt 中用 `@图1` 指代。
- vid prompt 以选中确认图作为身份和画面锚点，再写动作、镜头、节奏和画面质感。

## 命令

```bash
python3 TOOLS/dreamina_prompt.py TEMP/RUN_ID/vid-prompt.txt --route anna --channel auto --out TEMP/RUN_ID/dreamina-vid-prompt.txt
python3 TOOLS/generation_gate.py --engine dreamina --route anna --channel auto --reference-url "REFERENCE_URL" --grid-report TEMP/RUN_ID/reference-grid-report.json --prompt-file TEMP/RUN_ID/dreamina-vid-prompt.txt --confirmation-image TEMP/RUN_ID/confirm-A-HHMMSS/A-01/SELECTED.png --out-dir TEMP/RUN_ID/logs/generation-gate
dreamina multimodal2video --image TEMP/RUN_ID/confirm-A-HHMMSS/A-01/SELECTED.png --prompt "$(cat TEMP/RUN_ID/dreamina-vid-prompt.txt)" --model_version seedance2.0_vip --ratio 9:16 --video_resolution 720p --duration 5
```

## 重试

- 同一确认图和同一 prompt 最多自动提交 2 次，包含第一次提交和最多一次自动收敛或原样重提。
- TNS/安全拦截后的收敛版本必须重新运行 `prompt_lint.py` 和 `generation_gate.py --tns-retry`。

## 通过标准

- Dreamina vid prompt 只含 `@图1`。
- `generation_gate.py` 结论为 `pass`。
- 下载到的 MP4 可解码、竖屏、约 5-6 秒，并整理为 `OUTPUT/RUN_ID.mp4`。
