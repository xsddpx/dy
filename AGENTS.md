# Repository Guidelines

## 项目结构

`DOCS/PROJECT.md` 是跨阶段项目合同；`DOCS/PIPELINE/` 按编号保存视频主链，`DOCS/WORKFLOWS/` 保存独立工作流，`DOCS/RUNBOOKS/` 保存按需调用的修复手册。Python 与 Shell 自动化位于 `TOOLS/`，测试位于 `TOOLS/tests/`，稳定素材和数据账本位于 `MATERIAL/`。运行目录、成片命名及流程硬阻断统一查阅 `DOCS/PROJECT.md`，不要在本文件重复维护。

## 开发与测试命令

- `zsh TOOLS/setup_env.sh`：创建或修复项目 `.venv` 并安装依赖。
- `.venv/bin/python -m pytest TOOLS/tests -q`：运行完整测试套件。
- `.venv/bin/python -m pytest TOOLS/tests/test_run_workspace.py -q`：运行单个测试模块。

所有命令从 Git 仓库根目录执行，使用 `.venv/bin/python`，不要写死 macOS 用户名或调用系统 Python。

## 编码风格与测试规范

Python 使用四空格缩进；函数和文件采用 `snake_case`，测试类采用 `PascalCase`，常量采用 `UPPER_SNAKE_CASE`。CLI 使用 `argparse`，公开辅助函数在有助于理解时添加类型标注。Shell 脚本沿用所在文件既有的 zsh 或 POSIX 风格。项目未配置统一格式化工具，应保持相邻代码风格并控制改动范围。

测试使用 `unittest` 的断言和 mock，由 pytest 收集。测试文件命名为 `test_<模块>.py`，方法命名为 `test_<行为>`。CLI 校验、文件系统状态和发布适配器修改应补充离线回归测试。项目未设置覆盖率阈值，但评审前必须保证全量测试通过。

## 提交与拉取请求

提交标题应简短、使用祈使语气，可采用 `feat:`、`fix:`、`docs:` 或 `refine:` 前缀。每个提交只处理一个明确主题。拉取请求需说明流程影响、列出已运行测试并关联相关 issue；仅在界面或生成资产变化时附截图。不得提交 `.env`、浏览器配置、凭据、`TEMP/` 或 `OUTPUT/` 媒体文件。

## Agent 启动与汇报

启动时依次读取本文件、`DOCS/PROJECT.md`、`~/.codex/AGENTS.md`，再按项目路由读取当前阶段、独立工作流或运行手册。默认使用中文，只汇报已验证结果。生成任务按“成片信息、Google Drive 链接、最终 prompt、生成与 TNS 状态”汇报；仅在用户明确要求时内嵌媒体。

会话交付中，只要已附上 Google Drive 链接，就不再展示、附上或链接任何图片（包括代理图和原图）。未附 Drive 链接且正文已展示代理图时，不再展示、附上或链接原图；原图仅保留在本地，只在用户明确要求时提供。
