# 主链 03：视频生成与交付

## 生成合同

统一入口读取不可变 `logs/contracts/generation-vN.json` 后提交 Dreamina；命令参数不再由调用者重复维护。清单锁定配置哈希、prompt 哈希、严格有序的两张绝对路径参考图、模型、9:16、720p 和 5/6/7 秒时长。

入口自动轮询同一 `submit_id`，使用递增间隔并把详细响应写入 `logs/dreamina/`。TNS 只触发衣柜版本收敛，最多到 v5；网络、登录、积分、上传、下载、参数和超时归类为环境错误并停在可恢复状态。

## 质检与正式成片

- `xdy` 自动生成固定角色代理图，以及视频 `0.5 秒 / 中点 / 结束前 0.5 秒` 三帧；每张小于 100KB，并写 `quality/quality-checklist.json`。
- 执行者必须逐张视觉对照，只判断胸部体量是否相对固定角色图明显偏小。通过记录 `pass`，明显偏小记录 `blocked`。
- `xdysp` 不生成质检代理图、不执行内容质检，记录 `not_performed`，由用户本人检查成片。

```bash
.venv/bin/python TOOLS/xdy_flow.py record-quality "$RUN_ID" pass
# 或 blocked / not_performed
```

通过或明确跳过质检后，同一原子操作复制正式 MP4、对照源/目标 SHA-256、执行 ffprobe 校验，并写唯一 `output/created`。正式输出仍固定为 `OUTPUT/RUN_ID.mp4`。

## Google Drive 根目录

产生正式成片后，`status/resume` 返回连接器上传请求：源文件固定为本次 OUTPUT，文件名为 `RUN_ID.mp4`，MIME 为 `video/mp4`，不传父文件夹 ID。连接器上传后必须回读 My Drive 根目录，再把真实结果交给：

```bash
.venv/bin/python TOOLS/xdy_flow.py record-drive "$RUN_ID" --result @result.json
```

成功结果必须包含正确文件名、MIME、大小、`file_id` 或 `url` 以及 `root_verified=true`；出现任何目标子文件夹字段均拒绝记录。失败结果必须包含原因和 `needs_retry=true`。已记录终态时重复调用幂等，内容不同则拒绝改写。

Drive 失败不阻断 xdy 发布，但必须保留补传状态。没有正式成片的失败路线只能记录 `not_attempted`。
