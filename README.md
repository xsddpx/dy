## 规则

- README 只保留简短 DAG。
- 流程变化后及时更新 DAG。

```mermaid
flowchart TD
  A["启动读取"] --> B["建档"]
  B --> C["行程确认"]
  C --> D["选题 + 衣柜 + Prompt"]
  D --> E["Dreamina 生成"]
  E --> F["质检"]
  F --> G["抖音 + 快手发布"]
  G --> H["记录收尾"]
```
