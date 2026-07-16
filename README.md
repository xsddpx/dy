## 规则

- README 只保留简短 DAG。
- 流程变化后及时更新 DAG。

```mermaid
flowchart TD
  A["启动读取"] --> B["建档"]
  B --> C["核心卖点 + 衣柜 + Prompt"]
  C --> D["Dreamina 生成"]
  C --> H["衣柜图三图实验"]
  H --> I["成对验证 + 记录"]
  D --> E["质检"]
  E --> F["抖音 + 快手发布"]
  F --> G["记录收尾"]
```
