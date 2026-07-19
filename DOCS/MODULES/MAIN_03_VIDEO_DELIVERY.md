# 主链 03：视频生成与交付

## 生成合同

统一入口读取不可变 `logs/contracts/generation-vN.json` 后提交 Dreamina；命令参数不再由调用者重复维护。清单锁定配置哈希、prompt 哈希、严格有序的两张绝对路径参考图、模型、9:16、720p 和 5/6/7 秒时长。

入口自动轮询同一 `submit_id`，使用递增间隔并把详细响应写入 `logs/dreamina/`。TNS 只触发衣柜版本收敛，最多到 v5；网络、登录、积分、上传、下载、参数和超时归类为环境错误并停在可恢复状态。

## 质检与正式成片

- `xdy` 从固定角色图顶部 52% 生成最大 960px 宽的身体参考带，保留正面、斜侧面、侧面和背面身体视图；另取视频 `0.5 秒 / 中点 / 结束前 0.5 秒` 三帧。每张代理图小于 100KB，并写 `quality/quality-checklist.json`。
- 执行者先以可读尺寸查看角色身体参考带，再按与成片相近的正面、斜侧面或侧面朝向逐张对照。以肩宽和胸廓为相对尺度，判断胸部体量、胸廓前后比例与侧向投影，不按画面中的绝对像素面积判断。
- 质检范围固定且仅包含上述胸部体量一致性。至少一帧必须清晰可判断；任一清晰可判断帧相对角色图明显偏小，或三帧均无法判断时，记录 `blocked`；其余记录 `pass`。
- 默认不检查、不评价、不汇报脸部身份、手指、肢体、服装、道具、动作、画面异常或 prompt 还原度；只有用户另行明确指定其他检查项时才扩展质检范围。
- `xdysp` 正常流程不生成质检代理图、不执行内容质检，记录 `not_performed`，由用户本人检查成片；用户事后要求质检时，临时按上述同规格生成角色身体参考带与首中尾三帧，但不改写运行记录中的 `not_performed`，并同样只检查胸部体量，除非用户明确指定其他检查项。

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
