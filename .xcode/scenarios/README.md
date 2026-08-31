# Xcode Scenarios

⚠️ **重要**：这些 scenarios 不应该直接放在 xcode 项目下。

Xcode 插件的设计是：
1. Cursor / VSCode 打开**被解读的项目**（如 `tong-ontology`）
2. 插件自动检测当前 workspace
3. scenarios 写到 `<workspace>/.xcode/scenarios/`（**被解读的项目里**）
4. scenario 用相对路径定位目标项目代码
5. xcode trace runner 用 `sys.settrace` 自动 trace 所有函数

## 怎么用

### 1. 在被解读的项目里创建 `.xcode/` 目录

```bash
cd /path/to/your-project
xcode init
```

这会创建：
```
your-project/
└── .xcode/
    ├── scenarios/    # scenario 脚本
    └── traces/       # trace 输出
```

### 2. 用 Agent 生成 scenario

打开 Cursor 里的 Agent 对话框：

> "测试这个项目里的 main 功能"

Agent 会调用 `markdown-ontology-extractor` sub-agent 生成 scenario 到 `your-project/.xcode/scenarios/`。

### 3. 跑 scenario

```bash
xcode run-scenario my_test
```

或点 Cursor 插件的 Run 按钮。

## Scenario 编写规范

⚠️ Scenario **应该独立运行**，不依赖 xcode 的位置。

```python
#!/usr/bin/env python3
"""scenario: <name> — <description>."""

# ✅ 推荐：相对路径定位目标项目
SCENARIO_FILE = os.path.abspath(__file__)
SCENARIOS_DIR = os.path.dirname(SCENARIO_FILE)
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCENARIOS_DIR))
TARGET_DIR = os.path.join(PROJECT_ROOT, "src")

# ✅ 推荐：只 import 标准库 + 目标项目公开 API
import os, re, json
from pathlib import Path

# ❌ 不要 import 目标项目的内部 trace 模块（如 @TracedAs）

# ✅ 用 sys.settrace 自动 trace（xcode 自动加）
def main():
    # 你的测试代码
    pass

if __name__ == "__main__":
    main()
```
