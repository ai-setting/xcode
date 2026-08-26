/**
 * Common types for xcode sub-modules.
 */

export type FailureCategory =
  | "syntax"
  | "import"
  | "business"
  | "trace-runner"
  | "unknown";

export interface TraceEntry {
  id?: number;
  call_id?: number;
  type?: "call" | "return" | "exception";
  func?: string;
  func_name?: string;
  qualname?: string;
  file: string;
  line: number;
  depth: number;
  caller?: {
    caller_id?: number | null;
    caller_file?: string;
    caller_line?: number;
    caller_func?: string;
  };
  caller_file?: string;
  caller_line?: number;
  args?: unknown;
  return_value?: unknown;
  exception?: string;
  duration_ms?: number;
}

export interface TraceResult {
  success: boolean;
  entries: TraceEntry[];
  output_path?: string;
  duration_ms: number;
  error?: string;
  /** raw stdout/stderr for debugging */
  raw_stdout?: string;
  raw_stderr?: string;
}

export interface FailureAnalysis {
  category: FailureCategory;
  reason: string;
  fix_hint: string;
}

export interface RunOptions {
  workspace: string;
  react: boolean;
  maxAttempts: number;
  description?: string;
}

export interface GenOptions {
  description: string;
  workspace: string;
  language: "python" | "typescript" | "go" | "rust";
}

export interface TraceOptions {
  output: string;
  filter: string[];
  maxDepth: number;
}
