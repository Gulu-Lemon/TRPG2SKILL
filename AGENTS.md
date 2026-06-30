# TRPG2SKILL 项目规则

## 项目概述
TRPG2SKILL 是一个 AI 驱动的 TRPG 世界书→SKILL 编译器 + 游戏运行时。
Python 3.12+, Flask Web, Jinja2 模板, httpx LLM 客户端。

## Loop Engineering 行为规则
所有工作必须遵循五阶段循环：**Discover → Plan → Execute → Verify → Iterate**

### 阶段规则
1. **Discover**: 先搜索代码库理解现状，再动手。使用 grep/glob 定位相关代码。
2. **Plan**: 向用户展示修改计划，获得确认后再执行。
3. **Execute**: 一次只改一个逻辑单元，保持和现有代码风格一致。
4. **Verify**: 每次修改后运行 `python -m pytest tests/test_integration.py -v`。
5. **Iterate**: 根据 Verify 结果决定继续/回退/停止。记录到 STATE.md。

### 架构约束
- `core/` — LLM 客户端、数据结构、配置管理，不依赖 Flask
- `compiler/` — 5 阶段编译管线：parse → analyze → validate → map → generate
- `runtime/` — 游戏引擎：7 步循环 (read_state → route → tool → narrative → pause → process → write_state)
- `web/` — **主要开发目标**：Flask Web 服务器 + 前端 SPA
- `generated/` — 编译输出 (gitignored)
- `issues/` — 代码审查发现的 20 个问题 (6 Critical + 9 Suggestion + 5 Architecture)

### 开发方向
- **CLI 模式 (`main.py play`) 已暂停开发。** 不再新增 CLI 功能，不再修复 CLI 特有 bug。
- 今后所有新功能仅投入 Web 模式 (`main.py serve` + `web/`)。
- `compile` 模式作为编译管线公共入口，CLI 和 Web 共用，继续维护。
- `setup` 模式仅用于首次配置，保持现状。

### 编码规范
- 使用类型注解 (Python 3.12+)
- 函数/方法使用 docstring
- 异常不静默吞掉，至少 log 再抛
- 禁止 monkey-patch 标准库/第三方类
- API Key 必须通过配置文件管理，不硬编码

### 测试规范
- 集成测试在 `tests/test_integration.py`
- 新增功能必须添加对应的测试用例
- 运行测试: `python -m pytest tests/test_integration.py -v`
- 提交前确保全部测试通过

### 状态管理
- 读取 STATE.md 了解当前循环进度
- 每次迭代后更新 STATE.md
- 任务列表通过 todowrite 工具管理
