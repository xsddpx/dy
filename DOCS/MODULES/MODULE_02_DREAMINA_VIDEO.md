# 模块 02：Dreamina 视频生成

## 职责

使用模块 01 派生的 vid prompt 和当前模式锁定的参考图提交 Dreamina 并下载 MP4。默认模式继续使用固定角色图与固定环境图；衣柜图实验模式在两者之间增加一张衣柜人台商品图。`xdy` 完成胸部体量质检后整理正式成片，`xdysp` 跳过内容质检直接整理正式成片；两条路线只要生成正式成片都上传 Google Drive，再分别进入发布或记录收尾。

## 输入合同与命令

- 固定使用两张图片输入：`MATERIAL/fixed-role/anna.png` 是第一张图，prompt 以 `@图1` 指代；`TEMP/RUN_ID/environment-path.txt` 中锁定的环境图是第二张图，prompt 以 `@图2` 指代。同一次运行的图片路径和顺序固定。
- `TEMP/RUN_ID/vid-prompt-v1.txt` 必须由模块 01 的 `derive --mode fast` 生成并通过校验；内容不合格时回模块 01 重写 `grid-prompt.txt`。
- 图片使用绝对路径提交；`--duration` 按画面节奏选择 `5`、`6` 或 `7`。

```bash
ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"
ENV_IMAGE="$(cat "TEMP/$RUN_ID/environment-path.txt")"
test -f "$ENV_IMAGE"

dreamina multimodal2video \
  --image "$ROOT_DIR/MATERIAL/fixed-role/anna.png" \
  --image "$ENV_IMAGE" \
  --prompt "$(cat "TEMP/$RUN_ID/vid-prompt-v1.txt")" \
  --model_version seedance2.0_vip \
  --ratio 9:16 \
  --video_resolution 720p \
  --duration 5
```

衣柜图实验模式固定使用三张图片，顺序不得交换：

1. `MATERIAL/fixed-role/anna.png`：`@图1`，只锚定人物身份和身材。
2. `TEMP/RUN_ID/wardrobe-image-path.txt`：`@图2`，只锚定服装，不继承人台、姿势或棚拍背景。
3. `TEMP/RUN_ID/environment-path.txt`：`@图3`，只锚定环境、机位和光影。

成对实验先设置本次同步版本，并校验锁定的三张输入；基线与三图必须分别读取自己的版本化 prompt：

```bash
ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"
PROMPT_VERSION="${PROMPT_VERSION:-1}"
WARDROBE_IMAGE="$(cat "TEMP/$RUN_ID/wardrobe-image-path.txt")"
ENV_IMAGE="$(cat "TEMP/$RUN_ID/environment-path.txt")"
test -f "$WARDROBE_IMAGE"
test -f "$ENV_IMAGE"
(cd / && shasum -a 256 -c "$ROOT_DIR/TEMP/$RUN_ID/reference-inputs.sha256")

dreamina multimodal2video \
  --image "$ROOT_DIR/MATERIAL/fixed-role/anna.png" \
  --image "$ENV_IMAGE" \
  --prompt "$(cat "TEMP/$RUN_ID/baseline-vid-prompt-v${PROMPT_VERSION}.txt")" \
  --model_version seedance2.0_vip \
  --ratio 9:16 \
  --video_resolution 720p \
  --duration 5

dreamina multimodal2video \
  --image "$ROOT_DIR/MATERIAL/fixed-role/anna.png" \
  --image "$WARDROBE_IMAGE" \
  --image "$ENV_IMAGE" \
  --prompt "$(cat "TEMP/$RUN_ID/three-image-vid-prompt-v${PROMPT_VERSION}.txt")" \
  --model_version seedance2.0_vip \
  --ratio 9:16 \
  --video_resolution 720p \
  --duration 5
```

衣柜图实验模式提交前，基线必须用 `prompt_lint.py --reference-mode standard` 通过校验，三图必须用 `prompt_lint.py --reference-mode wardrobe-image` 通过校验；两臂版本号必须相同，并用 `reference-inputs.sha256` 核对三张图片路径、顺序和文件哈希与模块 01 锁定值一致。当前本机 CLI 支持重复 `--image` 且图片上限为 9 张，因此三图输入处于客户端能力范围内；这不替代成片视觉验证。

默认跳过模块 00。网络、登录、积分、参数、上传、下载或超时等环境问题转模块 00 做最小修复并复测原失败点。

## 成片整理与胸部体量质检

- `xdy`：从临时 MP4 抽取首段、中段、尾段三张代理图，建议约为 `0.5s`、视频中点和结尾前 `0.5s`；另从固定角色图制作一张代理图。每张均小于 `100KB`，仅用于 Codex 视觉检查。
- `xdy`：执行者亲自逐张打开三帧并与固定角色代理图对照，不能只依赖脚本或平台预览；仅胸部体量明显偏小时阻断，其余全部通过。硬门通过后，将临时 MP4 整理为 `OUTPUT/RUN_ID.mp4`，并记录代理图和人工结论。
- `xdysp`：Dreamina 成功返回并下载原始 MP4 后，直接整理为 `OUTPUT/RUN_ID.mp4`；不抽取代理帧，不执行内容审查或视频质检，运行记录将质检状态写为 `not_performed`，成片由用户本人检查。
- 两条路线的发布、归档和交付始终使用 `OUTPUT/RUN_ID.mp4` 对应的原始 MP4。

## Google Drive 上传与发布路由

- `xdy` 或 `xdysp` 只要整理出 `OUTPUT/RUN_ID.mp4`，就使用已连接的 Google Drive 应用将本次正式原始 MP4 上传到 My Drive 根目录；不转换格式，不从 `TEMP/` 或旧 `OUTPUT/` 推断文件。
- 上传源文件使用 `OUTPUT/RUN_ID.mp4` 的绝对路径，目标文件名固定为 `RUN_ID.mp4`，MIME 类型使用 `video/mp4`；上传参数不传父文件夹 ID，等价于 `parent_folder_id = null`，不创建额外文件夹。
- 上传返回完成后，通过 My Drive 根目录列表或精确文件名搜索核对结果。同一 `RUN_ID`、同一正式成片已记录为上传成功时跳过重复上传；新 `RUN_ID` 或新成片继续上传。
- 在 `TEMP/RUN_ID/RUN_ID-run-record.jsonl` 记录 `google_drive/uploaded` 或 `google_drive/failed`。成功时记录文件名、文件 ID、URL、大小和修改时间等实际可用返回信息；无法取得的字段不虚构。
- 登录、权限、网络、配额、上传或核对失败时记录明确原因和 `needs_retry: true`。`xdy` 继续进入模块 03，`xdysp` 继续进入模块 04；Drive 失败不阻断后续流程。
- `xdy` 中用户明确要求“发布前确认”“只生成不发布”或“本次不用发布”时，Google Drive 自动上传仍执行；完成后在进入模块 03 前硬停，展示正式视频、首中尾帧、vid prompt、TNS 记录、Drive 上传状态和发布建议，取得明确授权后再进入模块 03。
- `xdysp` 完成 Drive 上传尝试后直接进入模块 04，不进入模块 03；最终展示正式视频、vid prompt、TNS 记录、Drive 上传状态和关键文件路径。

## TNS 重试

- `vid-prompt-v1.txt` 是首次提交。仅当 Dreamina 明确返回 TNS/安全拦截且没有可下载 MP4 时，才回模块 01 在固定合同内重选衣柜款式，生成 `vid-prompt-v2.txt` 至 `vid-prompt-v5.txt`。
- 每版重新运行 prompt lint，通过后再提交；固定 `@图1` 角色图、`environment-path.txt` 已锁定的 `@图2` 环境图、双图顺序和本次已选动作模板保持不变。
- 每次记录版本、prompt 路径、Dreamina 状态、失败原因和是否继续。到 `v5` 仍无产物时停止、不发布，并报告完整失败摘要。

衣柜图实验模式的 TNS 重试同样最多到 `v5`，但人物、衣柜图、环境图、三图顺序和各自文件哈希全部保持不变；只允许在模块 01 的安全合同内收敛款式文字，不得移除 `@图2` 服装角色约束或把环境改回 `@图2`。

## 衣柜图实验验证

正式替换双图主链前，使用 5–10 套具有不同领口、层次、裙裤轮廓、图案和袜类结构的衣柜图做成对验证。每组保持同一人物图、环境图、动作模板、模型、时长和分辨率，分别提交：

- 基线：人物图 + 环境图，使用安全的文字款式摘要。
- 实验：人物图 + 衣柜图 + 环境图，使用同一文字款式摘要和三图角色约束。

CLI 当前没有可锁定随机种子的参数，因此单组 A/B 不能证明稳定优势；必须依靠 5–10 套成对样本降低随机波动。两条实验视频分别保存为 `TEMP/RUN_ID/wardrobe-image-experiment/baseline/video-vN.mp4` 与 `TEMP/RUN_ID/wardrobe-image-experiment/three-image/video-vN.mp4`，不写入 `OUTPUT/`，不上传 Drive，不进入发布，并在同一 RUN_ID 记录每个 `vN` 的两臂任务 ID、prompt、输入哈希和终态，保留从 `v1` 到最终版本的完整链路。

逐组检查人物身份与身材、服装组件与结构、环境一致性、动作连续性、TNS 状态，以及是否泄漏人台形体、无头结构、白色棚拍背景或商品图站姿。三图方案只有在服装一致性明显优于基线，且人物、环境、动作和通过率没有明显退化时，才允许提出转为默认主链；否则保持实验分支并调整模块 05 的人台图标准或三图 prompt。
