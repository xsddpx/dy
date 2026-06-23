# 模块 02：Codex Image Gen 确认图与选择

## 职责

- 从参考帧生成强遮挡参考图。
- 用 `anna-upload-2k.jpg` 和强遮挡参考图调用 Codex 内置 `image_gen`。
- 每批固定生成 `A-01/A-02/A-03` 三个槽位。
- 从成功生成的槽位中选择唯一可用确认图，并记录选择结果。

## 输入与 @ 引用

- Codex Image Gen 先使用 `MATERIAL/fixed-role/anna-upload-2k.jpg` 作为角色参考图，在 prompt 中用 `@图1` 指代。
- 再使用本次强遮挡参考图，作为 `@图2`。
- `@图1` 提供人物身份、五官、脸型、发型和神态。
- `@图2` 提供姿态、动作、手部位置、镜头距离、构图关系和空间关系。
- `@图2` 中的遮挡块只是隐私处理，不生成到最终画面。

## 强遮挡参考图

- 从 `frame-*.png` 中选择最适合保留动作、镜头距离、手部位置、构图关系和空间关系的关键帧。
- 关键帧含人脸或可识别头脸特征时，先制作强遮挡参考图。
- 使用纯黑实心块覆盖原人物脸部，以及会暴露身份的头发区域。
- 遮挡时保留姿态、手势、镜头关系、构图关系和主要空间关系。
- 优先使用 `reference_mask.py --grid-report` 从 `reference-grid-report.json` 的人脸检测框自动生成遮挡图；工具会把 macOS Vision 的左下原点坐标换算为图像左上原点坐标，并扩张覆盖脸部和邻近头发区域。
- 自动检测缺失或遮挡框明显异常时，才使用 `--rect x,y,w,h` 手工兜底。
- 遮挡图统一保存为 `TEMP/RUN_ID/reference-masked.png`，报告保存为 `TEMP/RUN_ID/reference-masked-report.json`。

## img prompt

img prompt 用于确认图阶段，采用 `人物：`、`环境：`、`其他：` 三段式。每段都必须是 Codex Image Gen 可直接执行的画面描述，不写流程说明、合规说明或变化原因。执行者必须先为本批三张确认图设计环境方向，再写入 `环境：` 段；环境必须具体到空间类型、关键陈设、材质、光线来源、空间纵深和主体关系。

```text
人物：使用 @图1 的人物替换 @图2 中的人物。保持 @图1 的长相、五官、脸型、发型和神态；参考 @图2 的姿态、动作、手部位置、镜头距离、构图关系和空间关系。
环境：清晨的公寓客厅一角，浅灰布艺沙发在画面后侧，旁边有窄木边几、玻璃水杯、折叠瑜伽垫和一盆高叶绿植；白色纱帘透入柔和窗光，木地板有自然反光，空间整洁但有真实日常痕迹。
其他：@图2 中的黑色遮挡块只是隐私处理，不生成到最终画面。自然光影，构图稳定，画面物理真实。
```

同批三个槽位必须提前策划环境变化，并按变化幅度递进：

- `A-01` 环境轻度变化：保留参考的整体生活化气质和镜头关系，适合“同类用途但不同空间设计”。
- `A-02` 环境中度变化：改变空间类型或光线氛围，并增加可感知的陈设或空间层次；保持动作和主体关系清晰。
- `A-03` 环境明显变化：选择更有区别的生活化场景或空间叙事，背景层次、光线或站位关系明显拉开，但人物仍是画面主体。

三张图不能只是颜色、局部陈设或光线强弱的微调。轻度、中度、明显是执行者的策划标准，不写进最终 img prompt；最终 img prompt 只保留 `人物：`、`环境：`、`其他：` 三段可执行画面描述。`环境：` 不能只写“生活化空间”“自然光”“干净背景”等泛化词，必须给出可见物件、材质、光线位置和空间关系。人物身份始终以 `@图1` 为准，参考关系始终以 `@图2` 为动作、镜头关系、构图关系和空间关系来源。

## 生成与归档

```bash
python3 TOOLS/reference_mask.py TEMP/RUN_ID/frame-01.png --grid-report TEMP/RUN_ID/reference-grid-report.json --out TEMP/RUN_ID/reference-masked.png --report TEMP/RUN_ID/reference-masked-report.json
python3 TOOLS/confirmation_manifest.py ...
python3 TOOLS/confirmation_contact_sheet.py --manifest TEMP/RUN_ID/confirm-A-HHMMSS/confirmation-manifest.json --selected-slot A-02
python3 TOOLS/run_record.py append TEMP/RUN_ID/RUN_ID-run-record.jsonl --stage confirmation --event confirmation_selection --status selected --summary "确认图选择 A-02" --data '{"selected_slot":"A-02","selected_confirmation_image":"<manifest 中 A-02 的 image_path>","reason":"画面最稳定"}'
```

确认图生成使用当前 Codex 会话内置 `image_gen`。执行者必须先把 `@图1` 和 `@图2` 对应的本地图片载入当前 Codex 会话上下文，再调用内置 `image_gen`。每个槽位单独生成一次，并把生成得到的原始图片从 Codex 默认生成目录复制或移动到 `TEMP/RUN_ID/confirm-A-HHMMSS/raw/` 后再交给 `confirmation_manifest.py` 归档。

每个槽位写入 manifest 的 entry 采用以下稳定口径：

- `slot`：固定为 `A-01/A-02/A-03`。
- `submit_id`：固定为 `codex-imagegen-<STAMP>-<SLOT>`。
- `status`：生成成功为 `success`，失败为 `fail`。
- `image_path`：成功槽位指向对应 Codex Image Gen 原始图片。
- `model_version`：固定为 `codex-image-gen-built-in`。
- `prompt_path`：指向本槽位使用的 img prompt 文本。

## 确认图选择

- 执行者从 `A-01/A-02/A-03` 中选择一张成功生成、主体清晰、身份和画面可接受的确认图。
- 选择后必须记录 `selected_slot`、`selected_confirmation_image` 和简短 `reason`。
- 选中图作为模块 03 的唯一上传图，在 vid prompt 中用 `@图1` 指代。

## 通过标准

- `@图1` 对应 `anna-upload-2k.jpg`，`@图2` 对应强遮挡参考图。
- 强遮挡参考图已遮住原人物脸部和可识别头脸特征，并保留动作、镜头关系、构图关系和空间关系。
- `reference-masked-report.json` 已记录源图、输出图、遮挡模式和遮挡矩形；自动模式下还记录原始人脸检测框、坐标换算结果和扩张参数。
- 三个槽位编号固定为 `A-01/A-02/A-03`。
- 三个槽位的 img prompt 均使用 `人物：`、`环境：`、`其他：` 三段式；环境差异按轻度、中度、明显逐级增加，但最终 prompt 不写解释性变化标签。
- 每个 `环境：` 均已写清具体空间、关键陈设、材质、光线来源、空间纵深和主体关系。
- `confirmation-manifest.json/md` 已生成。
- 已记录确认图选择结果。
- `selected_confirmation_image` 指向 Codex Image Gen 原始确认图。
