# 模块 00：预检与文件归档

## 职责

- 确认本次任务是独立新任务。
- 检查 CDP Chrome、Dreamina CLI、抖音创作者中心登录态、文件读写和固定角色素材。
- 创建 `TEMP/RUN_ID/`，初始化运行记录。

## 必查项

- `TOOLS/open_cdp_chrome.sh` 可启动当前账户 CDP Chrome。
- `TOOLS/douyin_publish_preflight.py --cdp-url http://127.0.0.1:9222` 通过。
- `dreamina user_credit` 可查询账户积分。
- `MATERIAL/fixed-role/anna.png` 存在。
- `MATERIAL/fixed-role/anna-upload-2k.jpg` 是 2048x2048 JPG。
- `TEMP/`、`OUTPUT/` 可读写。

## 命名

- `RUN_ID`：`YYYYMMDD-HHmm-参考代号主题`。
- 过程文件写入 `TEMP/RUN_ID/`。
- 正式成片写入 `OUTPUT/RUN_ID.mp4`。
