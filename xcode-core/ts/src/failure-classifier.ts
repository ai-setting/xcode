/**
 * Failure classifier — categorizes a TraceResult into a FailureAnalysis
 * so the react-fix loop knows what to do.
 *
 * Categories:
 *   - syntax:        python indent / syntax / unbalanced quotes
 *   - import:        ModuleNotFoundError / ImportError
 *   - business:      runtime error in business logic (NameError, TypeError…)
 *   - trace-runner:  the trace runner itself failed (spawn, parse)
 *   - unknown:       empty trace / no clear signature
 */
import type { FailureAnalysis, TraceResult } from "./types.js";

const PATTERNS: Array<{
  category: FailureAnalysis["category"];
  re: RegExp;
  reason: (m: RegExpMatchArray) => string;
  hint: (m: RegExpMatchArray) => string;
}> = [
  {
    category: "syntax",
    re: /SyntaxError|IndentationError|invalid syntax|unexpected EOF|unterminated/i,
    reason: () => "Python syntax error",
    hint: () => "Check indentation, parentheses, and string quotes",
  },
  {
    category: "import",
    re: /No module named ['"]([^'"]+)['"]/i,
    reason: (m) => `Missing module: ${m[1]}`,
    hint: (m) => `Wrap the failing import in try/except or add ${m[1]} to sys.path`,
  },
  {
    category: "import",
    re: /ModuleNotFoundError|ImportError/i,
    reason: () => `ImportError / ModuleNotFoundError raised`,
    hint: () => "Wrap the failing import in try/except (or install the missing module)",
  },
  {
    category: "import",
    re: /No such file or directory.*\.py|cannot open .*\.py/i,
    reason: () => "Referenced .py file not found",
    hint: () => "Fix the import path or create the missing file",
  },
  {
    category: "business",
    re: /NameError|TypeError|ValueError|AttributeError|KeyError|IndexError|RecursionError/i,
    reason: (m) => `Runtime error (${m[0]})`,
    hint: () => "Add a try/except wrapper around the failing call",
  },
  {
    category: "trace-runner",
    re: /spawn python3 failed|xcode_trace\.py not found/i,
    reason: () => "xcode_trace.py itself failed to start",
    hint: () => "Verify python3 is installed and xcode_trace.py is on disk",
  },
];

export function classifyFailure(result: TraceResult): FailureAnalysis {
  const text = [result.error, result.raw_stderr, result.raw_stdout]
    .filter(Boolean)
    .join("\n");

  if (!text.trim() && result.entries.length === 0) {
    return {
      category: "unknown",
      reason: "Empty trace and no error message",
      fix_hint: "Verify the scenario's main() is actually being called",
    };
  }

  for (const p of PATTERNS) {
    const m = text.match(p.re);
    if (m) {
      return {
        category: p.category,
        reason: p.reason(m),
        fix_hint: p.hint(m),
      };
    }
  }

  // exit code != 0 but no signature → still business-ish
  return {
    category: "business",
    reason: text.split("\n").filter(Boolean).slice(-1)[0] || "unknown error",
    fix_hint: "Add an exception handler at the top of main()",
  };
}
