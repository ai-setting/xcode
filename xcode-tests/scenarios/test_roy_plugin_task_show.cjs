/**
 * roy-plugin-task-show Test Scenario
 *
 * Exercises the public, *non-VSCode* surface of the
 * @ai-setting/roy-plugin-task-show package so we can capture a trace tree
 * with `xcode trace ... --filter roy-plugin-task-show`.
 *
 * The script attaches every function it exercises to `module.exports`
 * so the trace runner's `Module._load` monkey-patch can wrap them.
 *
 * Covers:
 *   - EventBus.subscribe() / broadcast() / addListener() — pure JS, no deps
 *   - OperationsCache.get() / invalidate() / size() / clear() — with fake
 *     source factory
 *   - ToolCallCollector.recordToolCall() / listSessions() / size() — pure
 *     in-memory bookkeeping
 *   - formatSSEFrame() / writeSSEHeaders() — pure helpers
 *
 * Crucially, this scenario touches NO VSCode APIs, so it can run
 * under `xcode trace` (no GUI, no extension host).
 */

const PLUGIN_DIST =
  "/home/dzk/work/codework/personal/roy_world/roy-plugin-task-show/packages/roy-plugin-task-show/dist";

const {
  EventBus,
  formatSSEFrame,
  writeSSEHeaders,
  ToolCallCollector,
} = require(PLUGIN_DIST + "/index.js");
const { OperationsCache } = require(PLUGIN_DIST + "/operations-cache.js");

// ---------------------------------------------------------------------------
// Scenario body — exported so the trace runner's Module._load patch can wrap
// them.
// ---------------------------------------------------------------------------

function exerciseEventBus() {
  const bus = new EventBus();
  const received = [];
  const unsub = bus.addListener((event) => received.push(event));

  bus.broadcast({
    type: "task.created",
    taskId: 1,
    timestamp: Date.now(),
    pluginVersion: "2.6.6",
    data: { title: "demo task #1" },
  });
  bus.broadcast({
    type: "tool.recorded",
    taskId: 1,
    timestamp: Date.now(),
    pluginVersion: "2.6.6",
    data: { toolName: "bash", success: true, durationMs: 12 },
  });
  bus.broadcast({
    type: "task.completed",
    taskId: 1,
    timestamp: Date.now(),
    pluginVersion: "2.6.6",
    data: { status: "completed" },
  });

  unsub();
  bus.closeAll();

  const frame = formatSSEFrame({
    type: "task.created",
    taskId: 2,
    timestamp: Date.now(),
    pluginVersion: "2.6.6",
    data: { title: "fmt-test" },
  });

  const fakeRes = {
    statusCode: 0,
    setHeader() {},
    write() {},
  };
  writeSSEHeaders(fakeRes);

  return { broadcastCount: received.length, frameBytes: frame.length };
}

async function exerciseOperationsCache() {
  let calls = 0;
  const source = async (id) => {
    calls++;
    return {
      task: {
        id,
        title: `task-${id}`,
        status: "running",
        priority: "medium",
        type: "normal",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        tags: [],
      },
      operations: [
        {
          id: `${id}-op1`,
          type: "tool_call",
          title: `op-${id}`,
          status: "completed",
          startedAt: new Date().toISOString(),
        },
      ],
      fetchedAt: new Date().toISOString(),
      stale: false,
    };
  };

  const cache = new OperationsCache({ source, ttlMs: 60_000 });
  await cache.get(101);
  await cache.get(101); // cache hit, no source call
  await cache.get(202);
  cache.invalidate(101);
  await cache.get(101); // refetch after invalidate
  cache.clear();
  const size = cache.size();

  return { sourceCalls: calls, finalSize: size };
}

function exerciseCollector() {
  const cfg = {
    server: { host: "127.0.0.1", port: 7799 },
    maxStoredTasks: 50,
    autoOpen: false,
    heartbeatMs: 25_000,
  };
  const collector = new ToolCallCollector(cfg, { logPrefix: "scenario" });

  for (let i = 0; i < 3; i++) {
    collector.recordToolCall({
      toolName: ["bash", "read_file", "task_create"][i],
      args: { i, echo: i === 0 },
      success: true,
      outputPreview: `preview-${i}`,
      durationMs: 5 + i,
      timestamp: Date.now(),
      explicitTaskId: 42,
      iteration: i,
    });
  }

  collector.finalizeOnTaskUpdate({
    taskId: 42,
    newStatus: "completed",
    updatedAt: Date.now(),
  });

  const sessions = collector.listSessions();
  const sized = collector.size();

  return {
    recordedSessions: sessions.length,
    sessionSize: sized,
    firstTitle: sessions[0]?.title ?? "",
  };
}

async function runScenario() {
  const eb = exerciseEventBus();
  const oc = await exerciseOperationsCache();
  const cc = exerciseCollector();
  return { eb, oc, cc };
}

// Re-export the entry-points so the Module._load patch can wrap them. We
// also re-export the plugin symbols (so their method calls are captured)
module.exports = {
  runScenario,
  exerciseEventBus,
  exerciseOperationsCache,
  exerciseCollector,
  // Re-exports for the wrap-stage (so the runner sees them too)
  EventBus,
  OperationsCache,
  ToolCallCollector,
  formatSSEFrame,
  writeSSEHeaders,
};

// ---------------------------------------------------------------------------
// Top-level driver — invoked by the trace runner via the convention
// `runScenario()` / `runScenarioAsync()`. The runner awaits the returned
// promise before flushing the trace.
// ---------------------------------------------------------------------------

module.exports.runScenario = async function runScenarioAsync() {
  try {
    const res = await runScenario();
    console.log(JSON.stringify(res, null, 2));
  } catch (e) {
    console.error("[scenario] failed:", e);
    process.exit(1);
  }
};
module.exports.runScenarioAsync = module.exports.runScenario;

// ---------------------------------------------------------------------------
// When invoked directly (`node test_*.cjs`), fall back to self-execution.
// ---------------------------------------------------------------------------

if (require.main === module) {
  module.exports.runScenario();
}
