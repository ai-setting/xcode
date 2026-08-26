# Go Trace Scenario 示例

无侵入的 Go trace 示例。

## 工具选择

| 场景 | 工具 | 说明 |
|---|---|---|
| 生产级 trace | **`dlv trace`** (Delve) | 抓函数调用 + 入参 + 出参 |
| 全链路 trace | **`runtime/trace` + `go tool trace`** | scheduler + goroutine 可视化 |
| 简单 trace | 手动 `log.Printf` | 单行调试 |

## 文件

| 文件 | 场景 | 关键能力 |
|---|---|---|
| `simple_function.go` | 基础函数 | 单文件 / 顶层函数 |
| `class_methods.go` | 结构体方法 | receiver 方法 trace |
| `dlv_trace_demo.go` | Delve trace | 生产级 trace 演示 |

## 使用

### 方式 1：Delve trace（推荐）

```bash
# 编译
go build -o /tmp/myapp ./...

# dlv trace 抓所有 main.* 函数
dlv trace --output /tmp/trace.txt --regex 'main\.' /tmp/myapp arg1 arg2

# 抓指定包
dlv trace --regex 'mypkg\.Process' /tmp/myapp
```

### 方式 2：runtime/trace

```bash
go build -o /tmp/myapp ./...
/tmp/myapp            # 会生成 /tmp/trace.out
go tool trace /tmp/trace.out   # 浏览器打开可视化
```

### 方式 3：xcode trace runner

```bash
xcode trace xcode-core/examples/go/simple_function.go
```

## Delve 输出示例

```
> main.greet("World") => "Hello, World!"
> main.add(1, 2) => 3
```

每行包含：函数名 + 入参（JSON）+ 返回值。

## 注意事项

- 需要安装 Delve：`go install github.com/go-delve/delve/cmd/dlv@latest`
- 编译时不能 strip 符号，否则 dlv trace 抓不到行号
- regex 匹配函数签名，支持 `pkg.Function` / `pkg.(*Type).Method`
