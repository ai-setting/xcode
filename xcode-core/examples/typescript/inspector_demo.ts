/**
 * V8 Inspector Demo
 *
 * 运行：
 *   node --inspect-brk=0.0.0.0:9229 inspector_demo.ts
 *   # Chrome DevTools → chrome://inspect → Open dedicated DevTools for Node
 *
 * 抓取 call frame：
 *   inspector.Session 连接 9229，Debugger.enable + Debugger.setBreakpointByUrl
 */

import * as inspector from 'inspector';

interface CallFrame {
  functionName: string;
  url: string;
  lineNumber: number;
  columnNumber: number;
}

const session = new inspector.Session();
session.connect();

session.post('Debugger.enable', (err) => {
  if (err) {
    console.error('Debugger.enable failed:', err);
    return;
  }

  session.on('Debugger.paused', (msg) => {
    const callFrames = msg.params.callFrames || [];
    console.log('=== Paused ===');
    for (const frame of callFrames) {
      console.log(
        `  ${frame.functionName || '<anonymous>'} @ ${frame.url}:${frame.lineNumber}:${frame.columnNumber}`
      );
    }
    session.post('Debugger.resume');
  });

  // 业务代码
  function greet(name: string): string {
    return `Hello, ${name}!`;
  }
  function add(a: number, b: number): number {
    return a + b;
  }

  // 在 greet 第一行下断点
  const url = require('url').pathToFileURL(__filename).href;
  session.post(
    'Debugger.setBreakpointByUrl',
    {
      lineNumber: 36, // 'return `Hello, ${name}!`;' 行
      url,
    },
    (err2, res) => {
      if (err2) {
        console.error('setBreakpointByUrl failed:', err2);
        return;
      }
      console.log(`Breakpoint set, id=${res.breakpointId}`);
      console.log(greet('World'));
      console.log(add(1, 2));
    }
  );
});
