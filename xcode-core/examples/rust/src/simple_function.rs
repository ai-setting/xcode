// 简单函数 trace 示例

fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}

fn add(a: i32, b: i32) -> i32 {
    a + b
}

fn main() {
    println!("{}", greet("World"));
    println!("{}", add(1, 2));
}
