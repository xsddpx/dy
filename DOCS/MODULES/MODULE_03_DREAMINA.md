# 模块 03：Dreamina 确认图与自动选图

## 职责

- 从参考帧生成去身份图。
- 用 `anna-upload-2k.jpg` 和去身份参考图提交 Dreamina `image2image`。
- 每批固定生成 `A-01/A-02/A-03` 三个槽位。
- 用 `face_similarity_gate.py` 自动选择唯一可用确认图。

## 命令

```bash
dreamina image2image --images MATERIAL/fixed-role/anna-upload-2k.jpg,TEMP/RUN_ID/去身份图.png --prompt "..." --model_version 5.0 --ratio 9:16
python3 TOOLS/confirmation_manifest.py ...
python3 TOOLS/face_similarity_gate.py --manifest TEMP/RUN_ID/confirm-A-HHMMSS/confirmation-manifest.json --route anna --out TEMP/RUN_ID/confirm-A-HHMMSS/face-similarity-report.json
python3 TOOLS/confirmation_contact_sheet.py --manifest TEMP/RUN_ID/confirm-A-HHMMSS/confirmation-manifest.json --face-report TEMP/RUN_ID/confirm-A-HHMMSS/face-similarity-report.json
```

## 通过标准

- 三个槽位编号固定为 `A-01/A-02/A-03`。
- `confirmation-manifest.json/md` 已生成。
- `face-similarity-report.json` 的 `decision=pass`。
- `selected_confirmation_image` 指向 Dreamina 原始确认图。
