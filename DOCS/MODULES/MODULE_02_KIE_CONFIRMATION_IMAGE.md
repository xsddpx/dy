# 模块 02：slow 模式 Kie 确认图与确认

## 职责

- 本模块只属于显式 `slow` 模式，不属于默认 `/dy`、`dy`、`今天日更` 的 `auto/fast` 流程。
- 从模块 01 的 `grid-prompt.txt` 取用 img prompt 所需六段式标准块，生成一张 Kie 确认图。
- Kie Nano Banana Pro 1K 只上传 `MATERIAL/fixed-role/anna.png`。
- 每批固定只有 `A-01` 一个槽位。
- A-01 生成后必须硬停，等待用户明确确认是否使用该图。

## 输入与 @ 引用

- Kie 生图只上传 `MATERIAL/fixed-role/anna.png`，在 prompt 中用 `@图1` 指代。
- `@图1` 是同一位成年女性的多视角、多表情角色参考图，不是多人合照或多角色拼图。
- `@图1` 提供人物身份、五官、脸型、发型、神态和稳定身材比例；左下大脸和正面脸优先作为身份锚点，侧面、背面和表情小图只作为辅助参考。
- 模块 01 的 `reference-grid.jpg` 或帧图只作为人工视觉分析来源，分析结果集中写入 `grid-prompt.txt`；参考宫格、参考帧或其他参考图不得作为 Kie 视觉输入。
- 确认图阶段不得提交第二张图片，也不得在 img prompt 中引用第二张图片。

## Kie 配置

- 本地 `.env` 必须配置 `KIE_API_KEY`，不得提交 `.env`。
- 确认图模型固定为 `nano-banana-pro`。
- 输出规格固定为 `aspect_ratio=9:16`、`resolution=1K`、`output_format=png`。
- 本地角色图先通过 Kie File Stream Upload 获得临时 URL，再传入 `image_input`。
- Kie 临时 URL 有时效，生成成功后必须立即下载原始确认图到 `TEMP/RUN_ID/confirm-A-HHMMSS/raw/`，后续只使用本地文件路径。

## img prompt

img prompt 用于确认图阶段，使用模块 01 定义的六段式结构：

```text
人物：...
穿搭：...
姿态镜头：...
环境：...
卖点与锁定：...
其他：...
```

- `人物：`、`穿搭：`、`姿态镜头：`、`环境：`、`卖点与锁定：`、`其他：` 均从 `grid-prompt.txt` 对应标准块取用，并清理成 Kie 可直接执行的画面描述。
- `参考类型识别：`、`整体动画：`、`背景音乐：` 不进入 img prompt。
- 最终 img prompt 不得写 `参考类型=`、`主类型=`、`次类型=`、`grid-prompt.txt`、`reference-grid`、`参考宫格`、`类型判断依据`、流程说明、文件来源说明、分析过程或“根据/融合/吸收”等解释性表达。
- 若 `grid-prompt.txt` 的穿搭、姿态镜头、环境或卖点与锁定不够具体，必须回到模块 01 重新写好对应标准块，再提交 Kie。

## 生成前自检

提交 Kie 前，执行者必须检查最终 img prompt：

- 已使用六段式结构，并包含 `卖点与锁定：`。
- `穿搭：` 已包含服装类别、颜色、领口方向、左右肩臂、袖长、腰线、下装结构、开口方向、面料质感和裁切范围。
- 宫格为特殊或不对称穿搭时，prompt 已明确左右差异，不用 `不对称设计`、`特殊剪裁` 等词替代具体结构。
- `姿态镜头：` 已写清姿态、重心、手部位置、裁切、镜头距离、角度和封面姿态。
- `环境：` 已写清空间类型、背景物、材质、光线来源和人物与环境关系。
- 最终文本不含内部分析标签、文件名、来源说明、第二张图片引用或不可发布内容。

## 命令

```bash
python3 TOOLS/kie_confirmation_image.py --run-id RUN_ID --stamp YYYYMMDD-HHMM --batch A --slot A-01 --topic TOPIC --prompt-path TEMP/RUN_ID/A-01-img-prompt-v1.txt --out-dir TEMP/RUN_ID/confirm-A-HHMMSS
python3 TOOLS/confirmation_manifest.py --run-id RUN_ID --stamp YYYYMMDD-HHMM --batch A --topic TOPIC --out-dir TEMP/RUN_ID/confirm-A-HHMMSS --entry @TEMP/RUN_ID/confirm-A-HHMMSS/A-01-entry.json
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
- 输入来源必须说明 Kie 视觉输入只有 `MATERIAL/fixed-role/anna.png`，模块 01 的宫格或帧图仅作为人工视觉分析来源，最终 img prompt 来自 `grid-prompt.txt` 六段式标准块。
- 建议使用不等于用户确认；未获用户明确确认前，不得写入最终选图记录，不得进入 Dreamina 视频生成。
- 用户确认使用后，记录 `selected_slot=A-01`、`selected_confirmation_image`、选择原因和确认时间。
- 用户拒绝 A-01 时，当前 slow 流程停止；不得自动生成第二张、切换模式或接入其他路线。

## 通过标准

- Kie `image_input` 只包含 `MATERIAL/fixed-role/anna.png` 对应的临时 URL。
- img prompt 使用 `人物：`、`穿搭：`、`姿态镜头：`、`环境：`、`卖点与锁定：`、`其他：` 六段式。
- img prompt 已从 `grid-prompt.txt` 的标准块取用并清理为 Kie 可直接执行的文本。
- `A-01` 是本批唯一槽位；如发生 TNS 收敛，已保留 `v1-v5` 版本记录。
- `confirmation-manifest.json/md` 已生成，且只包含 A-01。
- A-01 原始确认图已下载到本地；展示时优先使用原始确认图，内部视觉检查如需代理图则仅用于检查，不作为正式产物。
- 用户明确确认后，`selected_confirmation_image` 指向 Kie 下载到本地的原始确认图。
