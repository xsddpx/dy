# 模块 03：Dreamina 确认图与自动选图

## 职责

- 从参考帧生成强遮挡参考图。
- 用 `anna-upload-2k.jpg` 和强遮挡参考图提交 Dreamina `image2image`。
- 每批固定生成 `A-01/A-02/A-03` 三个槽位。
- 用 `face_similarity_gate.py` 自动选择唯一可用确认图。

## 输入与 @ 引用

- Dreamina `image2image` 先上传 `MATERIAL/fixed-role/anna-upload-2k.jpg`，在 prompt 中用 `@图1` 指代。
- 再上传本次强遮挡参考图，作为 `@图2`。
- `@图1` 提供人物身份、五官、脸型、成熟气质和稳定身材比例。
- `@图2` 提供姿态、构图、头脸入镜范围、穿搭版型、动作和镜头距离。
- `@图2` 中的遮挡块只是隐私处理，不生成到最终画面。

## 强遮挡参考图

- 从 `frame-*.png` 中选择最适合保留动作、镜头距离、穿搭版型、手部位置和空间关系的关键帧。
- 关键帧含人脸或可识别头脸特征时，先制作强遮挡参考图。
- 使用纯黑实心块覆盖原人物脸部，以及会暴露身份的头发区域。
- 遮挡时保留身体姿态、手势、衣服结构、腰线、腿部入镜范围和主要空间关系。
- 优先使用 `reference_mask.py --grid-report` 从 `reference-grid-report.json` 的人脸检测框自动生成遮挡图；工具会把 macOS Vision 的左下原点坐标换算为图像左上原点坐标，并扩张覆盖脸部和邻近头发区域。
- 自动检测缺失或遮挡框明显异常时，才使用 `--rect x,y,w,h` 手工兜底。
- 遮挡图统一保存为 `TEMP/RUN_ID/reference-masked.png`，报告保存为 `TEMP/RUN_ID/reference-masked-report.json`。

## 确认图 prompt

确认图 prompt 采用正向引导：使用 `@图1` 的人物替换 `@图2` 中的人物，保持 `@图1` 的长相、五官、脸型、成熟气质和稳定身材比例；参考 `@图2` 的姿态、构图、头脸入镜范围、穿搭版型、动作和镜头距离；画面保持真实皮肤纹理、自然光影、真实面料质感和生活化空间。

```text
使用 @图1 的人物替换 @图2 中的人物。保持 @图1 的长相、五官、脸型、成熟气质和稳定身材比例；参考 @图2 的姿态、构图、头脸入镜范围、穿搭版型、动作和镜头距离。@图2 中的黑色遮挡块只是隐私处理，不生成到最终画面。画面呈现真实皮肤纹理、自然光影、真实面料质感和生活化空间，穿搭轮廓清晰，腰线可见，整体物理合理、平台可发布。
```

同批三个槽位可以围绕背景空间、光线、镜头距离、站位角度、穿搭细节或场景陈设做差异化探索，但人物身份始终以 `@图1` 为准，参考关系始终以 `@图2` 为动作和构图来源。

## 命令

```bash
python3 TOOLS/reference_mask.py TEMP/RUN_ID/frame-01.png --grid-report TEMP/RUN_ID/reference-grid-report.json --out TEMP/RUN_ID/reference-masked.png --report TEMP/RUN_ID/reference-masked-report.json
dreamina image2image --images MATERIAL/fixed-role/anna-upload-2k.jpg,TEMP/RUN_ID/reference-masked.png --prompt "..." --model_version 5.0 --ratio 9:16
python3 TOOLS/confirmation_manifest.py ...
python3 TOOLS/face_similarity_gate.py --manifest TEMP/RUN_ID/confirm-A-HHMMSS/confirmation-manifest.json --route anna --out TEMP/RUN_ID/confirm-A-HHMMSS/face-similarity-report.json
python3 TOOLS/confirmation_contact_sheet.py --manifest TEMP/RUN_ID/confirm-A-HHMMSS/confirmation-manifest.json --face-report TEMP/RUN_ID/confirm-A-HHMMSS/face-similarity-report.json
```

## 人脸一致性门禁

- `face_similarity_gate.py` 使用 `MATERIAL/fixed-role/anna.png` 作为本地比对源。
- 默认基础阈值为 `75%`。
- 候选确认图有人脸入镜时，门禁按有效脸部可见比例动态调整阈值。
- 候选确认图没有可比对人脸时，记录为脸部不入镜并跳过人脸一致性子门。
- 多张候选通过时，优先选择相似度 margin 更高、相似度更高、槽位顺序更靠前的确认图。
- `face-similarity-report.json` 必须保留为本次自动选图证据。

## 通过标准

- `@图1` 对应 `anna-upload-2k.jpg`，`@图2` 对应强遮挡参考图。
- 强遮挡参考图已遮住原人物脸部和可识别头脸特征，并保留动作、穿搭和构图信息。
- `reference-masked-report.json` 已记录源图、输出图、遮挡模式和遮挡矩形；自动模式下还记录原始人脸检测框、坐标换算结果和扩张参数。
- 三个槽位编号固定为 `A-01/A-02/A-03`。
- `confirmation-manifest.json/md` 已生成。
- `face-similarity-report.json` 的 `decision=pass`。
- `selected_confirmation_image` 指向 Dreamina 原始确认图。
