## 规则

- README 只保留简短 DAG。
- 流程变化后及时更新 DAG。

```mermaid
flowchart TD
  A["启动读取"] --> B["模块 04 启动建档：创建 RUN_ID"]
  B --> C["核心卖点 + 衣柜 + Prompt"]
  C --> D["Dreamina 生成"]
  D --> E["质检"]
  E --> F["抖音 + 快手发布"]
  F --> G["模块 04 记录收尾"]
```
