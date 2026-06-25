# 模块 02：slow 模式 Kie 确认图与确认

## 职责

- 本模块只属于显式 `slow` 模式，不属于默认 `/dy`、`dy`、`今天日更` 的 `auto/fast` 流程。
- 直接查看模块 01 生成的 `reference-grid.jpg` 或帧图，结合固定角色图生成一张 Kie 确认图。
- Kie Nano Banana Pro 1K 只上传 `MATERIAL/fixed-role/anna.png`。
- 每批固定只有 `A-01` 一个槽位。
- A-01 生成后必须硬停，等待用户明确确认是否使用该图。

## 输入与 @ 引用

- Kie 生图只上传 `MATERIAL/fixed-role/anna.png`，在 prompt 中用 `@图1` 指代。
- `@图1` 是同一位成年女性的多视角、多表情角色参考图，不是多人合照或多角色拼图。
- `@图1` 提供人物身份、五官、脸型、发型、神态和稳定身材比例；左下大脸和正面脸优先作为身份锚点，侧面、背面和表情小图只作为辅助参考。
- 模块 01 的 `reference-grid.jpg` 或帧图只作为人工视觉分析来源，用于提炼穿搭、环境、人物姿态和镜头关系；参考宫格、参考帧或其他参考图不得作为 Kie 视觉输入。
- `grid-prompt.txt` 不作为 slow 确认图 img prompt 的来源；img prompt 必须绕过 grid prompt，由执行者直接看宫格或帧图后人工重写。
- 确认图阶段不得提交第二张图片，也不得在 img prompt 中引用第二张图片。

## Kie 配置

- 本地 `.env` 必须配置 `KIE_API_KEY`，不得提交 `.env`。
- 确认图模型固定为 `nano-banana-pro`。
- 输出规格固定为 `aspect_ratio=9:16`、`resolution=1K`、`output_format=png`。
- 本地角色图先通过 Kie File Stream Upload 获得临时 URL，再传入 `image_input`。
- Kie 临时 URL 有时效，生成成功后必须立即下载原始确认图到 `TEMP/RUN_ID/confirm-A-HHMMSS/raw/`，后续只使用本地文件路径。

## img prompt

img prompt 用于确认图阶段，采用 `人物：`、`穿搭：`、`姿态镜头：`、`环境：`、`其他：` 五段式。每段都必须是 Kie Nano Banana Pro 可直接执行的画面描述，不写流程说明、合规说明或变化原因。

执行者必须直接查看模块 01 的 `reference-grid.jpg` 或帧图，重点分析可见穿搭、环境、人物姿态和镜头关系，再与 `@图1` 的角色身份规则人工重写成一张静态确认图。最终 img prompt 不得写 `参考类型=`、`主类型=`、`次类型=`、`grid-prompt.txt`、`参考宫格`、`类型判断依据`、流程说明、文件来源说明、分析过程或“根据/融合/吸收”等解释性表达。

```text
人物：@图1 是同一位成年女性的多视角、多表情角色参考图，不是多人合照；以 @图1 中左下大脸和正面脸为主要身份依据，侧面、背面和表情小图只用于辅助保持发型、脸型、身材比例和整体气质。画面中只出现这一位成年女性，保持 @图1 的长相、五官、脸型、发型、自然神态和稳定身材比例。
穿搭：修身浅色短上衣，领口与上身轮廓清晰，肩颈线条干净，上衣长度停在腰线上方，面料贴合但保持真实褶皱；高腰深色半裙包裹腰胯线条，腰线明确，整体穿搭成熟、生活化、完整着装。
姿态镜头：人物以正面略侧的站姿位于竖屏画面中部，身体重心自然落在一侧，手部轻轻整理外套边缘，镜头为半身到大半身构图，平视近景，裁切保留肩颈、上身轮廓、腰线和部分腿部入镜范围，画面适合做静态封面。
环境：清晨的公寓客厅一角，浅灰布艺沙发在画面后侧，旁边有窄木边几、玻璃水杯、折叠瑜伽垫和一盆高叶绿植；白色纱帘透入柔和窗光，木地板有自然反光，空间整洁但有真实日常痕迹。
其他：真实皮肤纹理，自然光影，真实面料质感，穿搭轮廓清晰，腰线可见，构图稳定，画面物理真实；不出现原视频人物身份、真人脸、账号标识、字幕水印、品牌商标或专有 IP。
```

写作规则：

- `人物：` 段必须声明 `@图1` 是同一人的多视角、多表情角色参考图，并指定左下大脸和正面脸为主要身份依据。
- `人物：` 段只写角色身份、五官、发型、脸型、神态和稳定身材比例，不写来源解释。
- `穿搭：` 段必须直接来自宫格或帧图的可见画面分析，写清衣服类别、颜色、领口、肩臂露出、上衣长度、腰线、裙裤形态、面料贴合和外搭层次；参考不清晰时只写可确认部分，不脑补品牌或不可见细节。
- `姿态镜头：` 段必须直接来自宫格或帧图的可见画面分析，写清站坐姿、侧身或前倾、重心、手部位置、裁切、镜头距离、角度、固定或手持关系和封面姿态。
- `环境：` 段必须直接来自宫格或帧图的可见画面分析，写清空间类型、背景物、家具或道具、材质、光线来源、空间纵深和人物与环境关系。
- 表情保持自然，承接宫格或帧图里可见的表情节奏；参考不清晰时使用 `@图1` 的自然神态，不默认生成笑脸。
- img prompt 默认不展开描述具体品牌或不可发布内容，只写可见画面、动作、镜头、场景和画面质感。

## 命令

```bash
python3 TOOLS/kie_confirmation_image.py --run-id RUN_ID --stamp YYYYMMDD-HHMM --batch A --slot A-01 --topic TOPIC --prompt-path TEMP/RUN_ID/A-01-img-prompt-v1.txt --out-dir TEMP/RUN_ID/confirm-A-HHMMSS
python3 TOOLS/confirmation_manifest.py --run-id RUN_ID --stamp YYYYMMDD-HHMM --batch A --topic TOPIC --out-dir TEMP/RUN_ID/confirm-A-HHMMSS --entry @TEMP/RUN_ID/confirm-A-HHMMSS/A-01-entry.json
python3 TOOLS/confirmation_contact_sheet.py --manifest TEMP/RUN_ID/confirm-A-HHMMSS/confirmation-manifest.json
```

`kie_confirmation_image.py` 为 A-01 生成一个 entry JSON，`submit_id` 对应 Kie `taskId`，`model_version` 固定为 `nano-banana-pro-1K`。失败时仍写 entry JSON，并记录失败原因，供 manifest 保留占位。

## TNS 收敛

- 确认图初稿固定为 `A-01-img-prompt-v1.txt`；`v1` 是首次提交。
- 只有 Kie 明确返回 TNS/安全拦截且 A-01 没有生成可下载图片时，才允许继续写 `A-01-img-prompt-v2.txt` 到 `A-01-img-prompt-v5.txt` 逐步收敛并重提。
- A-01 成功生成可用确认图后，停止图片 TNS 收敛并进入确认图硬停；不得为追求更多候选继续重提。
- 到 `v5` 仍因 TNS/安全拦截未生成时，停止，不进入 Dreamina 视频生成。
- 网络、登录、积分、参数错误、上传失败、超时、Kie 返回非 TNS 失败等不进入 `v2-v5` 收敛，按硬阻断报告。
- 每次 TNS 尝试必须记录版本号、prompt 路径、Kie 返回状态、失败原因和是否进入下一版；最终交付时报告最高尝试版本。

## 确认图硬停

- A-01 生成后必须向用户展示确认图、输入来源、img prompt、TNS 收敛记录和是否建议使用。
- 输入来源必须说明 Kie 视觉输入只有 `MATERIAL/fixed-role/anna.png`，模块 01 的宫格或帧图仅作为人工视觉分析来源。
- 建议使用不等于用户确认；未获用户明确确认前，不得写入最终选图记录，不得进入 Dreamina 视频生成。
- 用户确认使用后，记录 `selected_slot=A-01`、`selected_confirmation_image`、选择原因和确认时间。
- 用户拒绝 A-01 时，当前 slow 流程停止；不得自动生成第二张、切换模式或接入其他路线。

## 通过标准

- Kie `image_input` 只包含 `MATERIAL/fixed-role/anna.png` 对应的临时 URL。
- img prompt 使用 `人物：`、`穿搭：`、`姿态镜头：`、`环境：`、`其他：` 五段式；最终文本不含内部分析标签、文件名、流程说明、来源说明或第二张图片引用。
- `穿搭：`、`姿态镜头：` 和 `环境：` 均已直接来自宫格或帧图的可见画面分析，未读取或依赖 `grid-prompt.txt`。
- `A-01` 是本批唯一槽位；如发生 TNS 收敛，已保留 `v1-v5` 版本记录。
- `confirmation-manifest.json/md` 已生成，且只包含 A-01。
- A-01 原始确认图已下载到本地，代理图或接触表仅用于展示。
- 用户明确确认后，`selected_confirmation_image` 指向 Kie 下载到本地的原始确认图。
