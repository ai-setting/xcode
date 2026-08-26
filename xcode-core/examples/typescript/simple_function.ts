/**
 * 简单函数 trace 示例
 * 用 console.log 模拟 trace
 */

function greet(name: string): string {
  return `Hello, ${name}!`;
}

function add(a: number, b: number): number {
  return a + b;
}

console.log(greet("World"));
console.log(add(1, 2));
