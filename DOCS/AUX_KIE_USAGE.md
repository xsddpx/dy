# AUX：Kie 图生图使用方法

使用模型 `gpt-image-2-image-to-image`，输入图顺序固定为人物图、可选环境图。

## 配置

依赖：`requests`、`python-dotenv`。在仓库根目录 `.env` 中配置密钥，不要提交该文件：

```dotenv
KIE_API_KEY=
```

所有请求使用：

```text
Authorization: Bearer <KIE_API_KEY>
```

## 调用流程

### 1. 上传参考图

```text
POST https://kieai.redpandaai.co/api/file-stream-upload
Content-Type: multipart/form-data
字段：file、uploadPath、fileName
```

分别上传人物图和环境图，从响应 `data.downloadUrl` 读取 URL，并兼容 `data.fileUrl`。

### 2. 创建任务

```text
POST https://api.kie.ai/api/v1/jobs/createTask
Content-Type: application/json
```

请求体：

```json
{
  "model": "gpt-image-2-image-to-image",
  "input": {
    "prompt": "<PROMPT>",
    "input_urls": ["<ROLE_URL>", "<ENVIRONMENT_URL>"],
    "aspect_ratio": "auto"
  }
}
```

成功时读取 `data.taskId`。如需回调，在最外层增加 `callBackUrl`。

### 3. 轮询任务

```text
GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<TASK_ID>
```

- `waiting`、`queuing`、`generating`：继续轮询；
- `success`：下载结果；
- `fail`：记录 `failMsg` 或 `failCode` 后停止；
- 其他状态：报错停止。

建议每 `3` 秒轮询一次，最长等待 `900` 秒，单次请求超时 `60` 秒。

### 4. 下载结果

解析响应中的 `resultJson`，依次兼容 `resultUrls`、`urls`、`images`，下载第一个非空 URL，并确认文件大小大于 `0`。

成功时保存原图、`taskId`、请求参数和原始任务响应。Kie 明确失败时记录失败信息；认证、网络、上传、响应格式、下载或超时异常应与模型失败分开记录。

正式使用前进行一次小额 smoke test，确认模型名、请求字段和计费规则有效。

## 官方帮助

- [Kie GPT Image 2 图生图官方文档](https://docs.kie.ai/cn/market/gpt/gpt-image-2-image-to-image)
