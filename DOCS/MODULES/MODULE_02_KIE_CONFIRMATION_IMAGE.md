# 模块 02：slow 模式 Kie 确认图与确认

## 职责

- 本模块只属于显式 `slow` 模式，不属于默认 `/dy`、`dy`、`今天日更` 的 `auto/fast` 流程。
- 从模块 01 的十段式 `grid-prompt.txt` 派生 img prompt，生成一张 Kie 确认图。
- Kie `gpt-image-2-image-to-image` 只上传 `MATERIAL/fixed-role/anna.png`。
- 每批固定只有一个 `*-01` 槽位，首批为 `A-01`。
- 当前批次确认图生成后必须硬停，等待用户明确确认是否使用该图。
- 用户说“换一个”“换一张”或明确拒绝当前确认图时，在同一 `RUN_ID`、同一参考和同一 `grid-prompt.txt` 下生成下一批单槽位确认图，例如 `B-01`；不得进入 Dreamina，不得切换模式，不得更换参考。

## 输入与 @ 引用

- Kie 生图只上传 `MATERIAL/fixed-role/anna.png`，在 prompt 中用 `@图1` 指代。
- `@图1` 是同一位成年女性的多视角、多表情角色参考图，不是多人合照或多角色拼图。
- `@图1` 提供人物身份、五官、脸型、发型、神态和稳定身材比例；左下大脸和正面脸优先作为身份锚点，侧面、背面和表情小图只作为辅助参考。
- 模块 01 的 `reference-grid.jpg` 或帧图只作为人工视觉分析来源，最终画面描述集中写入 `grid-prompt.txt`；参考宫格、参考帧或其他参考图不得作为 Kie 视觉输入。
- 确认图阶段每次 Kie 提交不得提交第二张图片，也不得在 img prompt 中引用第二张图片。

## Kie 配置

- 本地 `.env` 必须配置 `KIE_API_KEY`，不得提交 `.env`。
- 确认图模型固定为 Kie `gpt-image-2-image-to-image`。
- Kie 提交参数使用 `input_urls` 传入角色图临时 URL，`aspect_ratio=auto`；竖屏画面由 img prompt 的竖屏构图、车门/站台构图要求锁定。
- 本地角色图先通过 Kie File Stream Upload 获得临时 URL，再传入 `input_urls`。
- Kie 临时 URL 有时效，生成成功后必须立即下载原始确认图到 `TEMP/RUN_ID/confirm-BATCH-HHMMSS/raw/`，后续只使用本地文件路径。

## img prompt

img prompt 的内容规范只看模块 01，不在本模块维护单独模板。

- 本模块只执行阶段裁剪：从 `TEMP/RUN_ID/grid-prompt.txt` 删除完整的 `整体动画：` 段和完整的 `背景音乐：` 段，得到当前槽位的 `TEMP/RUN_ID/SLOT-img-prompt-v1.txt`，例如 `A-01-img-prompt-v1.txt` 或 `B-01-img-prompt-v1.txt`。
- 除删除上述两段外，其余段落不得在模块 02 临时重组、补写或改写。
- 派生结果必须仍是 Kie 可直接执行的静态画面描述；如果删除后出现断裂、矛盾、动态动作过强、第二张图片引用或内部说明，必须回到模块 01 重写 `grid-prompt.txt` 后重新派生。

## 生成前自检

提交 Kie 前，执行者必须检查最终 img prompt：

- `grid-prompt.txt` 已按模块 01 完成；如发现内容不够具体，只回到模块 01 修改。
- `SLOT-img-prompt-v1.txt` 只删除动画和音乐两段，其余文本与 `grid-prompt.txt` 保持一致。
- img prompt 不再包含动画段、音乐段、第二张图片引用、参考宫格输入语义或内部说明。
- Kie `input_urls` 只包含 `MATERIAL/fixed-role/anna.png` 对应的临时 URL。

## 命令

```bash
python3 TOOLS/kie_confirmation_image.py --run-id RUN_ID --stamp YYYYMMDD-HHMM --batch BATCH --slot SLOT --topic TOPIC --prompt-path TEMP/RUN_ID/SLOT-img-prompt-v1.txt --out-dir TEMP/RUN_ID/confirm-BATCH-HHMMSS
python3 TOOLS/confirmation_manifest.py --run-id RUN_ID --stamp YYYYMMDD-HHMM --batch BATCH --topic TOPIC --out-dir TEMP/RUN_ID/confirm-BATCH-HHMMSS --entry @TEMP/RUN_ID/confirm-BATCH-HHMMSS/SLOT-entry.json
```

`kie_confirmation_image.py` 为当前槽位生成一个 entry JSON，`submit_id` 对应 Kie `taskId`，`model_version` 固定为 `gpt-image-2-image-to-image`。失败时仍写 entry JSON，并记录失败原因，供 manifest 保留占位。

## TNS 收敛

- 确认图初稿固定为 `SLOT-img-prompt-v1.txt`；`v1` 是首次提交。
- 只有 Kie 明确返回 TNS/安全拦截且当前槽位没有生成可下载图片时，才允许继续写 `SLOT-img-prompt-v2.txt` 到 `SLOT-img-prompt-v5.txt` 逐步收敛并重提。
- 当前槽位成功生成可用确认图后，停止图片 TNS 收敛并进入确认图硬停；不得为追求更多候选继续重提。
- 到 `v5` 仍因 TNS/安全拦截未生成时，停止，不进入 Dreamina 视频生成。
- 网络、登录、积分、参数错误、上传失败、超时、Kie 返回非 TNS 失败等不进入 `v2-v5` 收敛，按硬阻断报告。
- 每次 TNS 尝试必须记录版本号、prompt 路径、Kie 返回状态、失败原因和是否进入下一版；最终交付时报告最高尝试版本。

## 确认图硬停

- 当前槽位生成后必须向用户展示确认图、输入来源、img prompt、TNS 收敛记录和是否建议使用。
- 输入来源必须说明 Kie 视觉输入只有 `MATERIAL/fixed-role/anna.png`，模块 01 的宫格或帧图仅作为人工视觉分析来源，最终 img prompt 由 `grid-prompt.txt` 删除动画和音乐两段得到。
- 建议使用不等于用户确认；未获用户明确确认前，不得写入最终选图记录，不得进入 Dreamina 视频生成。
- 用户确认使用后，记录 `selected_slot`、`selected_confirmation_image`、选择原因和确认时间。
- 用户拒绝当前槽位，或说“换一个”“换一张”时，记录当前槽位为 rejected，并生成下一批单槽位确认图；换图不改变参考、不改变 `grid-prompt.txt`、不进入 Dreamina。只有用户明确说停止时，才停止当前 slow 流程。

## 通过标准

- Kie `input_urls` 只包含 `MATERIAL/fixed-role/anna.png` 对应的临时 URL。
- img prompt 已由十段式 `grid-prompt.txt` 删除 `整体动画：` 和 `背景音乐：` 两段得到，并可作为 Kie 直接执行的文本。
- 当前 `*-01` 是本批唯一槽位；如发生 TNS 收敛，已保留 `v1-v5` 版本记录。
- `confirmation-manifest.json/md` 已生成，且只包含当前批次的单个 `*-01` 槽位。
- 当前槽位原始确认图已下载到本地；展示时优先使用原始确认图，内部视觉检查如需代理图则仅用于检查，不作为正式产物。
- 用户明确确认后，`selected_confirmation_image` 指向 Kie 下载到本地的原始确认图。
