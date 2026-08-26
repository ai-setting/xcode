# Python Trace Scenario 示例

无侵入的 Python trace 示例 — 直接运行，无需修改目标代码。

## 文件

| 文件 | 场景 | 关键能力 |
|---|---|---|
| `simple_function.py` | 基础函数 trace | 单文件 / 顶层函数 |
| `class_methods.py` | 类方法 trace | 含调用方位置（caller_file + caller_line） |
| `async_function.py` | async/await trace | 协程调用链 |
| `multi_file_call.py` | 跨文件调用链 | 多模块串联 |
| `module_a.py` / `module_b.py` | 多文件支持模块 | 配合 multi_file_call.py |

## 使用

### 方式 1：直接 trace（无侵入）

```bash
# 单文件
xcode trace xcode-core/examples/python/simple_function.py

# 输出到指定路径
xcode trace xcode-core/examples/python/class_methods.py --output /tmp/trace.json
```

### 方式 2：作为 scenario 模板

```bash
cd <your-project>
xcode init
# 把 simple_function.py / multi_file_call.py 当模板，
# 替换里面的 import 和函数调用
xcode run-scenario my_test
```

## 输出格式

`/tmp/xcode_traces/<name>.json` 含：

```json
{
  "entries": [
    {
      "type": "call",
      "func": "Calculator.add",
      "args": {"a": 1, "b": 2},
      "file": "class_methods.py",
      "line": 8,
      "caller_file": "class_methods.py",
      "caller_line": 25
    },
    {
      "type": "return",
      "func": "Calculator.add",
      "result": 3,
      "file": "class_methods.py",
      "line": 9
    }
  ]
}
```

每个 entry 含：
- **函数定义位置**（`file` + `line`）
- **调用方位置**（`caller_file` + `caller_line`）
- **入参**（`args`）
- **出参**（`result`）

## 注意事项

- 不需要修改目标项目代码 — `xcode` 使用 `sys.settrace` 无侵入注入
- 入口文件必须有 `if __name__ == '__main__':` 才能被 trace
- 异步函数需要 `asyncio.run()` 启动，trace 才能捕获
