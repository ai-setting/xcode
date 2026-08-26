/**
 * Preload script run by ts_trace_runner via `node --require=...`
 *
 * Responsibilities (in order):
 *   1. Install the Module._load monkey-patch BEFORE the target loads.
 *   2. Read --output / --max-depth / --filter-from-cli from process.argv.
 *   3. Require the target script. If it exports `runScenario` (sync) or
 *      `runScenarioAsync` (returns a Promise), call it; otherwise assume
 *      the script's top-level code self-executes (legacy convention).
 *   4. After the target settles, flush the trace JSON to --output and
 *      exit 0.
 *
 * The patch duplicates the XCodeTsTraceRunner class from ts_trace_runner.ts
 * so the preload stays a single self-contained CommonJS file.
 */

"use strict";
const Module = require("node:module");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

// ---------- arg parsing ---------------------------------------------------
function argAfter(name, defVal) {
  for (let i = 0; i < process.argv.length; i++) {
    if (process.argv[i] === name) {
      const next = process.argv[i + 1];
      if (next != null && !next.startsWith("--")) return next;
    }
  }
  return defVal;
}
const knownFlags = new Set(["--require", "--output", "--filter", "--max-depth", "--workspace"]);
let targetIdx = -1;
for (let i = 1; i < process.argv.length; i++) {
  const a = process.argv[i];
  if (knownFlags.has(a)) {
    i += 1;
    continue;
  }
  if (a.startsWith("--")) continue;
  targetIdx = i;
  break;
}
const TARGET_SCRIPT = targetIdx >= 0 ? process.argv[targetIdx] : "";
const OUTPUT = argAfter("--output", "/tmp/xcode_traces/ts_trace.json");
const MAX_DEPTH = parseInt(argAfter("--max-depth", "25"), 10);
const FILTER = (argAfter("--filter", "") || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);
const WORKSPACE = argAfter("--workspace", process.cwd());

// ---------- helpers -------------------------------------------------------
function rel(p, root) {
  const r = path.relative(root, p);
  return !r || r.startsWith("..") || path.isAbsolute(r) ? r : "./" + r;
}
function safe(v, max) {
  if (max == null) max = 500;
  if (v === undefined) return "undefined";
  if (v === null) return "null";
  if (typeof v === "string") return v.length > max ? v.slice(0, max) + "..." : v;
  if (typeof v === "function") return "<function " + (v.name || "anon") + ">";
  if (typeof v === "symbol") return String(v);
  try {
    const seen = new WeakSet();
    const s = JSON.stringify(
      v,
      (_k, val) => {
        if (val && typeof val === "object") {
          if (seen.has(val)) return "<circ>";
          seen.add(val);
        }
        if (typeof val === "function") return "<function>";
        return val;
      },
      2,
    );
    if (s == null) return "<undef>";
    return s.length > max ? s.slice(0, max) + "..." : s;
  } catch {
    return "<unserializable " + typeof v + ">";
  }
}
function getArgNames(fn) {
  const src = fn.toString();
  const m = src.match(/^[^(]*\(([^)]*)\)/);
  if (!m) return [];
  return m[1]
    .split(",")
    .map((p) => p.trim())
    .filter((p) => p.length > 0 && p !== "this")
    .map((p) => p.split(/[:=]/)[0].trim() || "arg");
}
function parseCallerStack() {
  const stack = new Error().stack;
  if (!stack) return null;
  const re = /\s+at\s+(.+?)\s+\((.+?):(\d+):(\d+)\)|^\s*at\s+(.+?):(\d+):(\d+)\s*$/;
  // Skip frames that belong to this preload's own infrastructure
  // (Error, parseCallerStack, the wrapper body itself). We pick the
  // first remaining frame as the user-side caller.
  const frames = stack.split("\n").slice(1); // drop the "Error\n" header
  const cleanupFile = (f) => (f || "").replace(/^file:\/*/, "");
  for (const raw of frames) {
    const line = raw.trimEnd();
    if (line.indexOf("_ts_trace_preload.cjs") >= 0) continue;
    const m = re.exec(line);
    if (m) {
      if (m[1] && m[2] && m[3])
        return { file: cleanupFile(m[2]), line: +m[3], func: m[1] };
      if (m[5] && m[6] && m[7])
        return { file: cleanupFile(m[5]), line: +m[6], func: "<anon>" };
    }
  }
  return null;
}

// ---------- AST index -----------------------------------------------------
function indexSource(file, source) {
  const sf = ts.createSourceFile(
    file,
    source,
    ts.ScriptTarget.ES2022,
    true,
    ts.ScriptKind.JS,
  );
  const byName = new Map();
  function visit(node, scope) {
    if (
      ts.isFunctionDeclaration(node) ||
      ts.isMethodDeclaration(node) ||
      ts.isFunctionExpression(node) ||
      ts.isArrowFunction(node)
    ) {
      const nameNode = node.name;
      const name = nameNode && ts.isIdentifier(nameNode) ? nameNode.text : undefined;
      if (name) {
        const line = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
        const qn = scope.concat(name).join(".");
        byName.set(qn, { line, qualname: qn });
      }
    }
    if (ts.isClassDeclaration(node) && node.name) {
      const cn = node.name.text;
      ts.forEachChild(node, (c) => visit(c, scope.concat(cn)));
      return;
    }
    ts.forEachChild(node, (c) => visit(c, scope));
  }
  visit(sf, []);
  return byName;
}

// ---------- trace state ---------------------------------------------------
const state = {
  entries: [],
  callId: 0,
  depth: 0,
  callStack: [],
  start: Date.now(),
  exceptionCount: 0,
  returnCount: 0,
  lastEnter: new Map(),
  sourceIndexCache: new Map(),
  wrapped: new WeakSet(),
  /** Map: original function → synthetic class-source AST index path. */
  protoFakePath: new WeakMap(),
};
function matchesFilter(q, f) {
  if (!FILTER.length) return true;
  for (const tok of FILTER) {
    if (q.includes(tok) || f.includes(tok)) return true;
  }
  return false;
}

// ---------- the patch -----------------------------------------------------
const origLoad = Module._load;
Module._load = function (request, parent, isMain, ...rest) {
  const exported = origLoad.call(this, request, parent, isMain, ...rest);
  try {
    wrapExports(exported, request, parent && parent.filename);
  } catch (e) {
    process.stderr.write(
      "[xcode-ts-trace] wrap failed for " + request + ": " + ((e && e.message) || e) + "\n",
    );
  }
  return exported;
};

function ensureIndex(filePath) {
  if (!filePath) return null;
  if (state.sourceIndexCache.has(filePath)) return state.sourceIndexCache.get(filePath);
  try {
    const src = fs.readFileSync(filePath, "utf8");
    const idx = indexSource(filePath, src);
    state.sourceIndexCache.set(filePath, idx);
    return idx;
  } catch {
    state.sourceIndexCache.set(filePath, null);
    return null;
  }
}
function resolveFile(request, parentFile) {
  if (!parentFile) return null;
  // For absolute paths, return them directly if they exist.
  if (path.isAbsolute(request) && fs.existsSync(request)) return request;
  try {
    const ModuleCtor = require("module");
    const m = new ModuleCtor(request, parentFile);
    const f = m.filename;
    if (f && fs.existsSync(f)) return f;
  } catch {}
  return null;
}
function makeWrapper(fn, qualname, filePath) {
  if (typeof fn !== "function") return null;
  let defLine = 0;
  let defQ = qualname;
  let pathForRel = filePath;
  if (filePath) {
    const idx = ensureIndex(filePath);
    if (idx) {
      const hit = idx.get(qualname) || idx.get(fn.name || "");
      if (hit) {
        defLine = hit.line;
        defQ = hit.qualname;
      }
    }
  }
  // If this is a class prototype method, the prototype was tagged with
  // a synthetic class-source path during wrapProto. Prefer that index
  // when the original file didn't have a hit.
  if (!defLine) {
    const fakePath = state.protoFakePath.get(fn);
    if (fakePath) {
      const idx = ensureIndex(fakePath);
      if (idx) {
        const hit = idx.get(qualname) || idx.get(fn.name || "");
        if (hit) {
          defLine = hit.line;
          defQ = hit.qualname;
          pathForRel = filePath; // keep the real file path for display
        }
      }
    }
  }
  const relFile = pathForRel ? rel(pathForRel, WORKSPACE) : "<unknown>";
  function wrapper() {
    const cf = parseCallerStack();
    const callerFile = (cf && cf.file) || "";
    const callerFunc = (cf && cf.func) || "<anon>";
    const callerLine = (cf && cf.line) || 0;
    const q = defQ || fn.name || "<anon>";
    const f = filePath || "<unknown>";
    // Filter check: if the user passed --filter and neither the callee nor
    // the caller match a token, skip recording (run fn as-is). This keeps
    // the trace tree narrow to user-relevant frames while preserving the
    // call/return semantics — non-traced frames are still visible as the
    // `caller` of the next traced frame.
    if (FILTER.length && !matchesFilter(q, f) && !matchesFilter(q, callerFile)) {
      return fn.apply(this, arguments);
    }
    // Filter check: if the user passed --filter and neither the callee nor
    if (state.depth >= MAX_DEPTH) {
      return fn.apply(this, arguments);
    }
    state.callId++;
    const id = state.callId;
    state.callStack.push(id);
    const args = Array.prototype.slice.call(arguments);
    const argNames = getArgNames(fn);
    const argMap = {};
    argNames.forEach((n, i) => (argMap[n || "arg" + i] = safe(args[i])));
    const entryTs = Date.now() - state.start;
    state.entries.push({
      id: id,
      type: "call",
      depth: state.depth,
      func: fn.name || "<anon>",
      qualname: q,
      file: relFile,
      line: defLine,
      args: argMap,
      caller: {
        caller_id: state.callStack[state.callStack.length - 2] || null,
        caller_file: callerFile ? rel(callerFile, WORKSPACE) : "<unknown>",
        caller_line: callerLine,
        caller_func: callerFunc,
      },
      timestamp: entryTs,
    });
    state.depth++;
    state.lastEnter.set(q, entryTs);
    try {
      const result = fn.apply(this, args);
      const now = Date.now() - state.start;
      state.depth--;
      state.callStack.pop();
      state.returnCount++;
      state.entries.push({
        id: id,
        type: "return",
        depth: state.depth,
        func: fn.name || "<anon>",
        qualname: q,
        file: relFile,
        line: defLine,
        return_value: safe(result),
        duration_ms: now - (state.lastEnter.get(q) || now),
        timestamp: now,
      });
      return result;
    } catch (err) {
      const now = Date.now() - state.start;
      state.depth--;
      state.callStack.pop();
      state.exceptionCount++;
      state.entries.push({
        id: id,
        type: "exception",
        depth: state.depth,
        func: fn.name || "<anon>",
        qualname: q,
        file: relFile,
        line: defLine,
        exception: ((err && err.name) ? err.name + ": " : "") + ((err && err.message) ? err.message : String(err)),
        timestamp: now,
      });
      throw err;
    }
  }
  try {
    Object.defineProperty(wrapper, "name", { value: fn.name || "<wrapped>" });
  } catch {}
  return wrapper;
}
function wrapExports(exp, request, parentFile) {
  if (exp == null) return;
  if (typeof exp !== "object" && typeof exp !== "function") return;
  if (state.wrapped.has(exp)) return;
  const filePath = resolveFile(request, parentFile);
  if (!filePath) return;
  ensureIndex(filePath);
  const keys = Object.keys(exp);
  for (const key of keys) {
    const v = exp[key];
    if (typeof v === "function") {
      // Try to wrap the export directly. Plain assignment AND
      // Object.defineProperty both fail on read-only ESM namespace objects,
      // so even when both throw we still continue: when the export is a
      // class, we wrap its prototype below.
      const w = makeWrapper(v, request + "." + key, filePath);
      if (w) {
        let assigned = false;
        try {
          exp[key] = w;
          assigned = true;
        } catch {
          try {
            Object.defineProperty(exp, key, {
              value: w,
              writable: true,
              configurable: true,
              enumerable: true,
            });
            assigned = true;
          } catch {}
        }
        // For class exports whose top-level symbol we can't replace
        // (ESM namespace is read-only), wrap the prototype methods in
        // place so future call-sites pick up the wrapped behaviour.
        if (!assigned && v && v.prototype) {
          wrapProto(v.prototype, key, filePath);
        }
      } else if (v && v.prototype) {
        // We couldn't wrap the export itself (e.g. undefined returned by
        // makeWrapper), still wrap the prototype methods so class
        // instances get traced.
        wrapProto(v.prototype, key, filePath);
      }
    }
  }
  if (typeof exp === "function" && exp.prototype) {
    wrapProto(exp.prototype, "", filePath);
  } else {
    state.wrapped.add(exp);
  }
}
function wrapProto(proto, className, filePath) {
  if (state.wrapped.has(proto)) return;
  // Build a synthetic AST index from the class's source string so we
  // can locate each method's def line even when the class itself was
  // re-exported (the namespace object we got from `require()` doesn't
  // carry the original source file in a way we can introspect, but
  // `proto.constructor.toString()` does).
  let fakePath = null;
  if (proto && proto.constructor && typeof proto.constructor.toString === "function") {
    try {
      const src = proto.constructor.toString();
      fakePath = "<class:" + (className || "anon") + ">";
      if (!state.sourceIndexCache.has(fakePath)) {
        state.sourceIndexCache.set(fakePath, indexSource(fakePath, src));
      }
    } catch {}
  }
  for (const key of Object.getOwnPropertyNames(proto)) {
    if (key === "constructor") continue;
    if (typeof proto[key] !== "function") continue;
    // Remember which proto method came from which class so makeWrapper
    // can pick the right AST index later.
    if (fakePath) state.protoFakePath.set(proto[key], fakePath);
    const qname = (className ? className + "." : "") + key;
    const w = makeWrapper(proto[key], qname, filePath);
    if (w) {
      try {
        proto[key] = w;
      } catch {}
    }
  }
  state.wrapped.add(proto);
}

// ---------- shutdown ------------------------------------------------------
function flushAndExit(code) {
  const totalCalls = state.entries.filter((e) => e.type === "call").length;
  const result = {
    success: state.entries.length > 0 && state.exceptionCount === 0,
    tool: "xcode-ts-trace",
    version: "0.1.0",
    target: path.resolve(TARGET_SCRIPT),
    filter: FILTER,
    max_depth: MAX_DEPTH,
    total_calls: totalCalls,
    total_returns: state.returnCount,
    total_exceptions: state.exceptionCount,
    duration_ms: Date.now() - state.start,
    entries: state.entries,
  };
  try {
    fs.mkdirSync(path.dirname(OUTPUT), { recursive: true });
    fs.writeFileSync(OUTPUT, JSON.stringify(result, null, 2));
  } catch (e) {
    process.stderr.write(
      "[xcode-ts-trace] failed to write output: " + ((e && e.message) || e) + "\n",
    );
  }
  if (result.total_exceptions > 0) code = 1;
  if (!TARGET_SCRIPT) code = 2;
  process.exit(code || 0);
}

// ---------- load the scenario --------------------------------------------
if (!TARGET_SCRIPT) {
  process.stderr.write("[xcode-ts-trace] no target script specified\n");
  flushAndExit(2);
}

(async function main() {
  let mod;
  try {
    mod = require(TARGET_SCRIPT);
  } catch (e) {
    state.exceptionCount++;
    state.entries.push({
      id: ++state.callId,
      type: "exception",
      depth: 0,
      func: "<script>",
      qualname: "<script>",
      file: path.resolve(TARGET_SCRIPT),
      line: 0,
      exception: ((e && e.name) ? e.name + ": " : "") + ((e && e.message) ? e.message : String(e)),
      timestamp: 0,
    });
    return flushAndExit(0);
  }

  // Convention: scenario exports `runScenario` (sync) or
  // `runScenarioAsync` (returns a Promise). If both exist we await the
  // async one. If neither exists, we assume the script's top-level
  // code self-executes and just defer one event-loop tick.
  try {
    if (typeof mod.runScenarioAsync === "function") {
      await mod.runScenarioAsync();
    } else if (typeof mod.runScenario === "function") {
      const r = mod.runScenario();
      if (r && typeof r.then === "function") await r;
    } else {
      // Wait one microtask + one setImmediate to let self-executing
      // top-level async work settle.
      await Promise.resolve();
      await new Promise((res) => setImmediate(res));
    }
  } catch (e) {
    state.exceptionCount++;
    state.entries.push({
      id: ++state.callId,
      type: "exception",
      depth: 0,
      func: "<scenario>",
      qualname: "<scenario>",
      file: path.resolve(TARGET_SCRIPT),
      line: 0,
      exception: ((e && e.name) ? e.name + ": " : "") + ((e && e.message) ? e.message : String(e)),
      timestamp: 0,
    });
  }

  // One more tick for any trailing microtasks.
  await new Promise((res) => setImmediate(res));
  flushAndExit(0);
})();
