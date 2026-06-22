# 模块 01：参考、去重与宫格

## 职责

- 接收用户指定参考，或从抖音收藏抽样。
- 对自主参考执行 7 天去重。
- 生成 6 帧参考宫格和报告。

## 命令

```bash
python3 TOOLS/reference_dedupe.py check "REFERENCE_URL" --window-days 7
python3 TOOLS/browser_reference_grid.py "REFERENCE_URL" --out-dir TEMP/RUN_ID/ --record-jsonl TEMP/RUN_ID/RUN_ID-run-record.jsonl
```

## 通过标准

- `reference-grid.jpg`、`reference-grid-report.json`、`reference-grid-report.md` 已写入 `TEMP/RUN_ID/`。
- 宫格报告 `decision=pass` 且 `validation.decision=pass`。
- 宫格只用于反推和记录，不作为 Dreamina 输入。
