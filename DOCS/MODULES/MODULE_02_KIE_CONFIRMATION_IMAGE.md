# 模块 02：slow 模式 Kie 确认图与选择

## 职责

- 本模块只属于显式 `slow` 模式，不属于默认 `/dy`、`dy`、`今天日更` 的 `auto/fast` 流程。
- 从参考帧生成强遮挡参考图。
- 用 `anna.png` 和强遮挡参考图提交 Kie Nano Banana Pro 1K 生图。
- 每批固定生成 `A-01/A-02` 两个槽位。
- 执行者从成功生成的确认图中选择唯一可用确认图。

## 输入与 @ 引用

- Kie 生图先上传 `MATERIAL/fixed-role/anna.png`，在 prompt 中用 `@图1` 指代。
- 再上传本次强遮挡参考图，作为 `@图2`。
- `@图1` 是同一位成年女性的多视角、多表情角色参考图，不是多人合照或多角色拼图。
- `@图1` 提供人物身份、五官、脸型、发型、神态和稳定身材比例；左下大脸和正面脸优先作为身份锚点，侧面、背面和表情小图只作为辅助参考。
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

## Kie 配置

- 本地 `.env` 必须配置 `KIE_API_KEY`，不得提交 `.env`。
- 确认图模型固定为 `nano-banana-pro`。
- 输出规格固定为 `aspect_ratio=9:16`、`resolution=1K`、`output_format=png`。
- 本地图片先通过 Kie File Stream Upload 获得临时 URL，再传入 `image_input`。
- Kie 临时 URL 有时效，生成成功后必须立即下载原始确认图到 `TEMP/RUN_ID/confirm-A-HHMMSS/raw/`，后续只使用本地文件路径。

## img prompt

img prompt 用于确认图阶段，采用 `人物：`、`环境：`、`其他：` 三段式。每段都必须是 Kie Nano Banana Pro 可直接执行的画面描述，不写流程说明、合规说明或变化原因。执行者必须先为本批两张确认图设计环境方向，再写入 `环境：` 段；环境必须具体到空间类型、关键陈设、材质、光线来源、空间纵深和主体关系。

```text
人物：@图1 是同一位成年女性的多视角、多表情角色参考图，不是多人合照；以 @图1 中左下大脸和正面脸为主要身份依据，侧面、背面和表情小图只用于辅助保持发型、脸型、身材比例和整体气质。使用 @图1 的人物替换 @图2 中的人物。保持 @图1 的长相、五官、脸型、发型、神态和稳定身材比例；参考 @图2 的姿态、身体角度、动作、手部位置、穿搭版型、腰线、腿部入镜范围和镜头距离。
环境：清晨的公寓客厅一角，浅灰布艺沙发在画面后侧，旁边有窄木边几、玻璃水杯、折叠瑜伽垫和一盆高叶绿植；白色纱帘透入柔和窗光，木地板有自然反光，空间整洁但有真实日常痕迹。
其他：@图2 中的黑色遮挡块只是隐私处理，不生成到最终画面。真实皮肤纹理，自然光影，真实面料质感，穿搭轮廓清晰，腰线可见，构图稳定，画面物理真实。
```

同批两个槽位必须提前策划环境变化，并按变化幅度递进：

- `A-01` 环境轻度变化：保留参考的整体生活化气质和镜头关系，适合“同类用途但不同空间设计”。
- `A-02` 环境中度变化：改变空间类型或光线氛围，并增加可感知的陈设或空间层次；保持动作和穿搭结构清晰。

两张图不能只是颜色、局部陈设或光线强弱的微调。轻度、中度是执行者的策划标准，不写进最终 img prompt；最终 img prompt 只保留 `人物：`、`环境：`、`其他：` 三段可执行画面描述。`人物：` 段必须声明 `@图1` 是同一人的多视角、多表情角色参考图，并指定左下大脸和正面脸为主要身份依据。`环境：` 不能只写“生活化空间”“自然光”“干净背景”等泛化词，必须给出可见物件、材质、光线位置和空间关系。人物身份始终以 `@图1` 为准，参考关系始终以 `@图2` 为动作、穿搭结构和镜头关系来源。

## 命令

```bash
python3 TOOLS/reference_mask.py TEMP/RUN_ID/frame-01.png --grid-report TEMP/RUN_ID/reference-grid-report.json --out TEMP/RUN_ID/reference-masked.png --report TEMP/RUN_ID/reference-masked-report.json
python3 TOOLS/kie_confirmation_image.py --run-id RUN_ID --stamp YYYYMMDD-HHMM --batch A --slot A-01 --topic TOPIC --reference-image TEMP/RUN_ID/reference-masked.png --prompt-path TEMP/RUN_ID/A-01-img-prompt.txt --out-dir TEMP/RUN_ID/confirm-A-HHMMSS
python3 TOOLS/kie_confirmation_image.py --run-id RUN_ID --stamp YYYYMMDD-HHMM --batch A --slot A-02 --topic TOPIC --reference-image TEMP/RUN_ID/reference-masked.png --prompt-path TEMP/RUN_ID/A-02-img-prompt.txt --out-dir TEMP/RUN_ID/confirm-A-HHMMSS
python3 TOOLS/confirmation_manifest.py --run-id RUN_ID --stamp YYYYMMDD-HHMM --batch A --topic TOPIC --out-dir TEMP/RUN_ID/confirm-A-HHMMSS --entry @TEMP/RUN_ID/confirm-A-HHMMSS/A-01-entry.json --entry @TEMP/RUN_ID/confirm-A-HHMMSS/A-02-entry.json
python3 TOOLS/confirmation_contact_sheet.py --manifest TEMP/RUN_ID/confirm-A-HHMMSS/confirmation-manifest.json
```

`kie_confirmation_image.py` 每个槽位生成一个 entry JSON，`submit_id` 对应 Kie `taskId`，`model_version` 固定为 `nano-banana-pro-1K`。失败槽位仍写 entry JSON，并记录失败原因，供 manifest 保留占位。

## 通过标准

- `@图1` 对应 `anna.png`，`@图2` 对应强遮挡参考图。
- 强遮挡参考图已遮住原人物脸部和可识别头脸特征，并保留动作、穿搭和构图信息。
- `reference-masked-report.json` 已记录源图、输出图、遮挡模式和遮挡矩形；自动模式下还记录原始人脸检测框、坐标换算结果和扩张参数。
- 两个槽位编号固定为 `A-01/A-02`。
- 两个槽位的 img prompt 均使用 `人物：`、`环境：`、`其他：` 三段式；`人物：` 段已声明 `@图1` 是同一人的多视角、多表情角色参考图，并以左下大脸和正面脸作为主要身份依据；环境差异按轻度、中度逐级增加，但最终 prompt 不写解释性变化标签。
- 每个 `环境：` 均已写清具体空间、关键陈设、材质、光线来源、空间纵深和主体关系。
- `confirmation-manifest.json/md` 已生成。
- `selected_confirmation_image` 指向 Kie 下载到本地的原始确认图。
