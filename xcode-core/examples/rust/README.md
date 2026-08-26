# Rust Trace Scenario 示例

无侵入的 Rust trace 示例。

## 工具选择

| 场景 | 工具 | 说明 |
|---|---|---|
| 生产级 trace | **`tracing` crate + `#[instrument]`** | 自动 span + field capture |
| 异步 trace | **`tokio-console`** | 实时查看 tokio task |
| 火焰图 | **`cargo-flamegraph`** | 性能 + 调用栈可视化 |

## 文件

| 文件 | 场景 | 关键能力 |
|---|---|---|
| `src/simple_function.rs` | 基础函数 | 单文件 / 顶层函数 |
| `src/class_methods.rs` | 结构体 impl | impl 块方法 trace |
| `src/tracing_demo.rs` | tracing 宏 | `#[instrument]` 自动 span |

## 使用

### 方式 1：tracing crate（推荐）

```bash
cargo build --example tracing_demo
cargo run --example tracing_demo
```

输出示例：

```
2024-01-15T10:30:00  INFO greet{name="World"}: xcode_examples: src/tracing_demo.rs:5: Greeting
2024-01-15T10:30:00  INFO greet{name="World"}: xcode_examples: close time.busy=1.2µs time.idle=1.5µs
Hello, World!
2024-01-15T10:30:00  INFO add{a=1, b=2}: xcode_examples: src/tracing_demo.rs:12: Adding
2024-01-15T10:30:00  INFO add{a=1, b=2}: xcode_examples: close time.busy=200ns time.idle=400ns
3
```

### 方式 2：火焰图

```bash
cargo install flamegraph
cargo flamegraph --example tracing_demo
# 浏览器打开 flamegraph.svg
```

### 方式 3：tokio-console（异步）

```bash
cargo install tokio-console
TOKIO_CONSOLE=1 cargo run --example tracing_demo
```

## 注意事项

- `#[instrument]` 自动记录函数入参和返回值
- `tracing_subscriber::fmt::init()` 必须在 main 第一行
- 异步函数需要 `#[instrument]` + `tokio::main`
