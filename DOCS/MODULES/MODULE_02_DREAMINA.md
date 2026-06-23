# 模块 02：Dreamina 确认图与自动选图

## 职责

- 从参考帧生成强遮挡参考图。
- 用 `anna-upload-2k.jpg` 和强遮挡参考图提交 Dreamina `image2image`。
- 每批固定生成 `A-01/A-02/A-03` 三个槽位。
- 用 `face_similarity_gate.py` 自动选择唯一可用确认图。

## 输入与 @ 引用

- Dreamina `image2image` 先上传 `MATERIAL/fixed-role/anna-upload-2k.jpg`，在 prompt 中用 `@图1` 指代。
- 再上传本次强遮挡参考图，作为 `@图2`。
- `@图1` 提供人物身份、五官、脸型、发型、神态和稳定身材比例。
- `@图2` 提供姿态、身体角度、动作、手部位置、穿搭版型、腰线、腿部入镜范围和镜头距离。
- `@图2` 中的遮挡块只是隐私处理，不生成到最终画面。

## 强遮挡参考图

- 从 `frame-*.png` 中选择最适合保留动作、镜头距离、穿搭版型、手部位置和空间关系的关键帧。
- 关键帧含人脸或可识别头脸特征时，先制作强遮挡参考图。
- 使用纯黑实心块覆盖原人物脸部，以及会暴露身份的头发区域。
- 遮挡时保留身体姿态、手势、衣服结构、腰线、腿部入镜范围和主要空间关系。
- 优先使用 `reference_mask.py --grid-report` 从 `reference-grid-report.json` 的人脸检测框自动生成遮挡图；工具会把 macOS Vision 的左下原点坐标换算为图像左上原点坐标，并扩张覆盖脸部和邻近头发区域。
- 自动检测缺失或遮挡框明显异常时，才使用 `--rect x,y,w,h` 手工兜底。
- 遮挡图统一保存为 `TEMP/RUN_ID/reference-masked.png`，报告保存为 `TEMP/RUN_ID/reference-masked-report.json`。

## img prompt

img prompt 用于确认图阶段，采用 `人物：`、`环境：`、`其他：` 三段式。每段都必须是 Dreamina 可直接执行的画面描述，不写流程说明、合规说明或变化原因。执行者必须先为本批三张确认图设计环境方向，再写入 `环境：` 段；环境必须具体到空间类型、关键陈设、材质、光线来源、空间纵深和主体关系。

```text
人物：使用 @图1 的人物替换 @图2 中的人物。保持 @图1 的长相、五官、脸型、发型、神态和稳定身材比例；参考 @图2 的姿态、身体角度、动作、手部位置、穿搭版型、腰线、腿部入镜范围和镜头距离。
环境：清晨的公寓客厅一角，浅灰布艺沙发在画面后侧，旁边有窄木边几、玻璃水杯、折叠瑜伽垫和一盆高叶绿植；白色纱帘透入柔和窗光，木地板有自然反光，空间整洁但有真实日常痕迹。
其他：@图2 中的黑色遮挡块只是隐私处理，不生成到最终画面。真实皮肤纹理，自然光影，真实面料质感，穿搭轮廓清晰，腰线可见，构图稳定，画面物理真实。
```

同批三个槽位必须提前策划环境变化，并按变化幅度递进：

- `A-01` 环境轻度变化：保留参考的整体生活化气质和镜头关系，适合“同类用途但不同空间设计”。
- `A-02` 环境中度变化：改变空间类型或光线氛围，并增加可感知的陈设或空间层次；保持动作和穿搭结构清晰。
- `A-03` 环境明显变化：选择更有区别的生活化场景或空间叙事，背景层次、光线或站位关系明显拉开，但人物仍是画面主体。

三张图不能只是颜色、局部陈设或光线强弱的微调。轻度、中度、明显是执行者的策划标准，不写进最终 img prompt；最终 img prompt 只保留 `人物：`、`环境：`、`其他：` 三段可执行画面描述。`环境：` 不能只写“生活化空间”“自然光”“干净背景”等泛化词，必须给出可见物件、材质、光线位置和空间关系。人物身份始终以 `@图1` 为准，参考关系始终以 `@图2` 为动作、穿搭结构和镜头关系来源。

## 命令

```bash
python3 TOOLS/reference_mask.py TEMP/RUN_ID/frame-01.png --grid-report TEMP/RUN_ID/reference-grid-report.json --out TEMP/RUN_ID/reference-masked.png --report TEMP/RUN_ID/reference-masked-report.json
dreamina image2image --images MATERIAL/fixed-role/anna-upload-2k.jpg,TEMP/RUN_ID/reference-masked.png --prompt "..." --model_version 5.0 --ratio 9:16 --resolution_type 2k
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
- 三个槽位的 img prompt 均使用 `人物：`、`环境：`、`其他：` 三段式；环境差异按轻度、中度、明显逐级增加，但最终 prompt 不写解释性变化标签。
- 每个 `环境：` 均已写清具体空间、关键陈设、材质、光线来源、空间纵深和主体关系。
- `confirmation-manifest.json/md` 已生成。
- `face-similarity-report.json` 的 `decision=pass`。
- `selected_confirmation_image` 指向 Dreamina 原始确认图。
