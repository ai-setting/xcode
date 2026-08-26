# TypeScript Trace Scenario 示例

无侵入的 TypeScript / Node.js trace 示例。

## 工具选择

| 场景 | 工具 | 说明 |
|---|---|---|
| 生产级 trace | **V8 Inspector Protocol** | 完整 call frame + 变量 |
| 调试级 trace | **Monkey patching** | 包装 console / module 函数 |
| 上下文传递 | **AsyncLocalStorage** | 跨 await 携带 trace context |

## 文件

| 文件 | 场景 | 关键能力 |
|---|---|---|
| `simple_function.ts` | 基础函数 | 单文件 / 顶层函数 |
| `monkey_patch_demo.ts` | 控制台拦截 | 演示 console.log monkey patch |
| `inspector_demo.ts` | V8 Inspector | 生产级 trace 入口模板 |

## 使用

### 方式 1：V8 Inspector（生产级）

```bash
# 启动 inspect 模式
node --inspect-brk=0.0.0.0:9229 inspector_demo.ts

# Chrome DevTools 连接 chrome://inspect
# 或：xcode 自动通过 Inspector Protocol 抓取 call frame
xcode trace --inspect inspector_demo.ts
```

### 方式 2：Monkey Patch（调试级）

```bash
npx ts-node monkey_patch_demo.ts
```

输出 `trace` 数组，含每次 console.log 的入参 + 时间戳。

### 方式 3：xcode trace runner

```bash
xcode trace xcode-core/ts/src/xcode_trace_runner.ts
```

## 注意事项

- V8 Inspector 需要 `--inspect-brk` 启动，DevTools 9229 端口
- Monkey patch 仅对同步代码生效，async 需用 AsyncLocalStorage
- 入口必须能 `node` 直接跑（不能依赖 tsc 编译）
