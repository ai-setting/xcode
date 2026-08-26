/**
 * Public entry for library consumers.
 */
export { XCodeTraceRunner } from "./trace-runner.js";
export { XCodeScenarioGen } from "./scenario-gen.js";
export { XCodeScenarioRunner } from "./scenario-runner.js";
export { classifyFailure } from "./failure-classifier.js";
export type {
  FailureAnalysis,
  FailureCategory,
  TraceEntry,
  TraceResult,
  RunOptions,
  GenOptions,
  TraceOptions,
} from "./types.js";
