---
name: xcode
description: |
  Use this skill whenever the user wants to:
  - trace / instrument / "show the call path" of a Python (or supported) project
  - run a "scenario" against a target git repo and produce a trace tree
  - debug a function flow end-to-end (entry → handler → business logic → output)
  The skill wraps the `xcode` CLI. The CLI itself handles react-fix retries;
  this skill describes the workflow and the failure taxonomy.
when_to_use: |
  - user says "trace this project's XXX flow"
  - user says "use xcode to test this scenario"
  - user says "show me the call tree of YYY in <repo>"
  - user wants to debug a function line that crosses several modules

allowed-tools: bash, read, edit, glob, grep, write
---

# xcode — non-invasive trace + AI scenario runner

## Overview

xcode is a two-layer tool:

1. **CLI layer** (`xcode-core/ts/dist/cli.js`): a thin commander-based
   CLI exposing `init / trace / gen-scenario / run-scenario / list /
   show-trace / serve`.
2. **React-fix runner**: `xcode run-scenario` runs the scenario under
   `xcode_trace.py` (a non-invasive Python tracer using `sys.settrace`),
   classifies any failure, and retries up to `N` times.

The runner is driven by the `xcode-scenario-runner` sub-agent (see
`xcode-core/agents/xcode-scenario-runner/`) — your job as the parent
agent is to dispatch and review.

---

## Quick start

```bash
# 1. install once (after `cd xcode-core/ts && npm install && npm run build`)
npm link                 # so `xcode` is on PATH

# 2. in the target project
cd <target-project>
xcode init                                       # creates .xcode/{scenarios,traces}/
xcode gen-scenario my_flow \
  --description "trace request → handler → DB layer" \
  --workspace .
xcode run-scenario my_flow                      # react-fix retries automatically
xcode show-trace my_flow                        # render trace tree
xcode serve                                      # http://localhost:7800
```

---

## CLI reference

| command                     | purpose                                                   |
| --------------------------- | --------------------------------------------------------- |
| `xcode serve`               | start the HTTP backend                                    |
| `xcode trace <script.py>`   | one-shot trace; writes JSON to `--output`                 |
| `xcode gen-scenario <name>` | generate a scenario script (LLM or template)              |
| `xcode run-scenario <name>` | run + react-fix; copies last-good trace to `.xcode/traces/` |
| `xcode list`                | list scenarios in `.xcode/scenarios/`                     |
| `xcode show-trace <name>`   | render the trace tree from `.xcode/traces/<name>.json`    |
| `xcode init`                | scaffold `.xcode/{scenarios,traces}/`                    |
| `xcode install`             | `npm link` + print sub-agent install instructions         |

---

## React-fix failure taxonomy

| category        | signature (regex)                                          | auto-fix strategy                   |
| --------------- | ---------------------------------------------------------- | ----------------------------------- |
| `syntax`        | `SyntaxError / IndentationError / invalid syntax`          | rewrap trailing block, ensure `if __name__ == "__main__": main()` |
| `import`        | `ModuleNotFoundError / ImportError / No module named X`    | wrap top-level imports in `try/except ImportError` |
| `business`      | `NameError / TypeError / ValueError / AttributeError`      | wrap main() in `try/except Exception`, print fallback |
| `trace-runner`  | `spawn python3 failed / xcode_trace.py not found`          | report (retry won't help; fix installation) |
| `unknown`       | (empty trace + no clear error)                             | verify main() is called              |

`xcode run-scenario` retries up to `--max-attempts 5` by default. After
that it prints each attempt's category + first error line — surface
this to the user instead of masking it.

---

## Sub-agent layout

```
xcode-core/
├── ts/                         # CLI source (commander.js)
│   └── src/{cli,trace-runner,scenario-gen,scenario-runner,failure-classifier}.ts
├── python/
│   ├── xcode_trace.py          # non-invasive Python tracer (sys.settrace)
│   └── xcode_server.py         # HTTP backend (FastAPI / flask)
├── agents/
│   └── xcode-scenario-runner/
│       ├── agent.yaml          # sub-agent manifest
│       └── prompt.md           # sub-agent system prompt
└── skills/
    └── xcode/
        └── SKILL.md            # ← you are here
```

The sub-agent manifest follows the code-reader convention
(`name / type / model / allowedTools / deniedTools`). Drop it into
`<roy-agent>/agents/xcode-scenario-runner/` and reference it as
`subagent_type: xcode-scenario-runner` from `delegate_task`.

---

## Caveats

- **xcode_trace.py uses `sys.settrace`** so it only works on Python.
  Other languages have their own tracer story (see the upstream
  `coder-reader trace` for `@TracedAs`-style instrumentation in TS/Go).
- **Scenarios must not modify project sources.** They are stand-alone
  scripts that import target modules and call them.
- **The template-mode scenario generator** skips LLM calls when
  `claude` is not on PATH. Provide `--description` so users always
  know what to fix manually if LLM mode is unavailable.
