/**
 * Monkey patch 演示：包装 console.log 模拟 trace
 */

interface CallEntry {
  type: 'call' | 'return';
  func: string;
  args?: string[];
  result?: string;
  file: string;
  line: number;
  timestamp: number;
}

const trace: CallEntry[] = [];
let depth = 0;

// 包装 console.log
const originalLog = console.log;
console.log = function (...args: any[]) {
  trace.push({
    type: 'call',
    func: 'console.log',
    args: args.map(String),
    file: 'runtime',
    line: 0,
    timestamp: Date.now(),
  });
  depth++;
  originalLog.apply(console, args);
  depth--;
  trace.push({
    type: 'return',
    func: 'console.log',
    file: 'runtime',
    line: 0,
    timestamp: Date.now(),
  });
};

function greet(name: string): string {
  return `Hello, ${name}!`;
}

greet("World");

console.log = originalLog;
console.log(`Total trace entries: ${trace.length}`);
