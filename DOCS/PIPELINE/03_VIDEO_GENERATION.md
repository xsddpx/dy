# 阶段 03：Dreamina 异步生成与下载

## 职责

使用阶段 02 已通过 lint 的 `vid-prompt-vN.txt` 和锁定的三张参考图提交 Dreamina，完整执行“提交 → 保存 `submit_id` → 查询终态 → 下载 MP4 → 记录结果”的异步闭环。

本阶段只把原始生成视频下载到 `TEMP/RUN_ID/`。内容质检、正式 `OUTPUT/RUN_ID.mp4`、Google Drive 上传和后续路由均由阶段 04 处理。

## 输入合同

- 阶段 01 已完成建档，本次 JSONL 的首条事件为 `run/started`。
- 当前版本文件固定为 `TEMP/RUN_ID/vid-prompt-vN.txt`，且已由阶段 02 的 `prompt_lint.py lint` 校验通过。
- 图片顺序固定为：
  1. `MATERIAL/fixed-role/anna.png`：`@图1`，只锚定人物身份和身材。
  2. `TEMP/RUN_ID/wardrobe-image-path.txt`：`@图2`，只锚定服装，不继承人台、姿势或棚拍背景。
  3. `TEMP/RUN_ID/environment-path.txt`：`@图3`，只锚定环境、机位和光影。
- 提交前使用 `reference-inputs.sha256` 核对三张图片的路径、顺序和文件哈希。`v1` 至 `v5` 不得换图、换款、换顺序、改动作模板或改写服装事实。
- `--duration` 按画面节奏选择 `5`、`6` 或 `7`；模型固定为 `seedance2.0_vip`，比例为 `9:16`，分辨率为 `720p`。

## 1. 准备本次版本

以下以首次提交 `v1` 为例；TNS 重试时只把 `VERSION` 改为下一版本：

```bash
ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

VERSION="v1"
DURATION="${DURATION:-5}"
PROMPT_FILE="TEMP/$RUN_ID/vid-prompt-$VERSION.txt"
ATTEMPT_DIR="TEMP/$RUN_ID/logs/dreamina/$VERSION"
DOWNLOAD_DIR="TEMP/$RUN_ID/downloads/$VERSION"
RECORD="TEMP/$RUN_ID/$RUN_ID-run-record.jsonl"

ROLE_IMAGE="$ROOT_DIR/MATERIAL/fixed-role/anna.png"
WARDROBE_IMAGE="$(cat "TEMP/$RUN_ID/wardrobe-image-path.txt")"
ENV_IMAGE="$(cat "TEMP/$RUN_ID/environment-path.txt")"

mkdir -p "$ATTEMPT_DIR" "$DOWNLOAD_DIR"
test -f "$PROMPT_FILE"
test -f "$ROLE_IMAGE"
test -f "$WARDROBE_IMAGE"
test -f "$ENV_IMAGE"
(cd / && shasum -a 256 -c "$ROOT_DIR/TEMP/$RUN_ID/reference-inputs.sha256")

.venv/bin/python TOOLS/prompt_lint.py lint \
  "$PROMPT_FILE" \
  --route anna \
  --channel auto \
  --reference-mode wardrobe-image \
  --out-dir "TEMP/$RUN_ID/logs/prompt-lint-$VERSION"
```

任一输入或 lint 不通过时返回阶段 02 修正当前版本；不得绕过校验提交。

## 2. 提交并保存 `submit_id`

```bash
dreamina multimodal2video \
  --image "$ROLE_IMAGE" \
  --image "$WARDROBE_IMAGE" \
  --image "$ENV_IMAGE" \
  --prompt "$(cat "$PROMPT_FILE")" \
  --model_version seedance2.0_vip \
  --ratio 9:16 \
  --video_resolution 720p \
  --duration "$DURATION" \
  | tee "$ATTEMPT_DIR/submit.json"
```

提交返回后必须立即从响应中取得非空 `submit_id`，写入本版本运行事件，并保留完整提交响应。响应是纯 JSON 时可执行：

```bash
SUBMIT_ID="$(.venv/bin/python -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["submit_id"])' \
  "$ATTEMPT_DIR/submit.json")"
test -n "$SUBMIT_ID"

.venv/bin/python TOOLS/run_record.py append "$RECORD" \
  --stage dreamina \
  --event submit \
  --status querying \
  --summary "Dreamina $VERSION 已提交" \
  --data "{\"version\":\"$VERSION\",\"prompt\":\"$PROMPT_FILE\",\"submit_id\":\"$SUBMIT_ID\",\"duration\":$DURATION,\"submit_log\":\"$ATTEMPT_DIR/submit.json\"}"
```

若提交端发生网络超时或连接中断且没有返回 `submit_id`，先执行 `dreamina list_task` 核对任务是否已经创建；找到对应任务后沿用其 `submit_id`，不得直接重复扣费提交。环境问题按 [`../RUNBOOKS/ENVIRONMENT_REPAIR.md`](../RUNBOOKS/ENVIRONMENT_REPAIR.md) 修复后返回同一失败点。

## 3. 使用同一个 `submit_id` 查询终态

首次及后续查询都使用本版本同一个 `submit_id`，日志按查询次序递增：

```bash
dreamina query_result \
  --submit_id "$SUBMIT_ID" \
  | tee "$ATTEMPT_DIR/query-01.json"
```

当 `gen_status=querying` 时继续调用 `query_result`，依次保存为 `query-02.json`、`query-03.json` 等；不要重新调用生成命令。查询传输失败时也优先复用同一个 `submit_id` 重查。

只有以下两种终态可以结束查询：

- `gen_status=success`，且 `result_json.videos` 中存在 MP4 结果。
- `gen_status=fail`，保留完整 `fail_reason` 和响应。

每次查询至少记录当前版本、`submit_id`、`gen_status`、队列状态或失败原因和查询日志路径。运行记录可以只追加关键状态变化，不必为连续相同的 `querying` 响应重复刷屏，但所有原始查询日志都要保留。

## 4. 成功后下载并核对

终态为 `success` 后，使用同一个 `submit_id` 和本版本下载目录再次查询并下载：

```bash
dreamina query_result \
  --submit_id "$SUBMIT_ID" \
  --download_dir "$DOWNLOAD_DIR" \
  | tee "$ATTEMPT_DIR/download.log"

find "$DOWNLOAD_DIR" -maxdepth 1 -type f -name '*.mp4' -print
```

必须确认实际 MP4 已落盘且可读，记录 Dreamina 返回的宽度、高度、时长、下载路径和结果日志。不得只看到 `success` 就跳过下载，也不得把远程 URL 当作正式成片。

成功事件至少包含：

- `version`
- `prompt`
- `submit_id`
- `gen_status=success`
- `tns=not_triggered`
- `downloaded`
- `width`、`height`、`duration`（Dreamina 实际返回时）
- `submit_log`、终态查询日志和下载日志

下载完成后进入阶段 04，仍由阶段 04 决定是否写入 `OUTPUT/RUN_ID.mp4`。

## 5. TNS `v1`–`v5` 收敛闭环

只有 Dreamina 明确返回 TNS/安全拦截，例如 `pre-TNS check did not pass`、`post-TNS check did not pass`，并且没有可下载 MP4 时，才进入下一版本：

1. 在本版本记录中写入 `gen_status=fail`、原始 `fail_reason`、`tns=triggered`、当前 prompt 路径、`submit_id`、终态查询日志和 `next_version`。
2. 返回阶段 02，在相同人物、衣柜、环境、哈希、服装事实和动作模板下直接写下一份 `vid-prompt-vN.txt`。
3. 对新版本执行对应 lint；通过后回到本阶段，建立新的版本目录并进行一次新提交。
4. `v1`、`v2`、`v3`、`v4`、`v5` 每版各自绑定唯一 prompt 路径、提交响应、`submit_id`、查询链和终态。
5. `v5` 仍被 TNS 拦截且没有 MP4 时停止生成，记录完整版本链并进入阶段 06，以失败终态收尾；不得创建正式成片或进入发布。

| Dreamina 状态 | 处理 |
|---|---|
| `querying` | 使用当前 `submit_id` 继续查询 |
| `success` 且有 MP4 | 下载、核对、记录，进入阶段 04 |
| 明确 TNS 且无 MP4，当前为 `v1`–`v4` | 记录终态，返回阶段 02 写下一版本 |
| 明确 TNS 且无 MP4，当前为 `v5` | 停止并进入阶段 06 失败收尾 |
| 网络、登录、积分、参数、上传、下载或超时 | 转环境修复；修复后复测原失败点 |
| 其他生成失败 | 记录原始失败原因并停止，不冒充 TNS 重写 prompt |

## 记录通过标准

进入阶段 04 前，本次成功版本必须同时具备：

- 已通过 lint 的 `vid-prompt-vN.txt`。
- 含 `submit_id` 的提交响应。
- 从 `querying` 到 `success` 的可审计查询链。
- 本地可读 MP4 下载路径。
- JSONL 中对应版本的提交、终态与下载结果。

阶段 06 最终汇总全部版本；失败版本不得被成功版本覆盖或删除。
