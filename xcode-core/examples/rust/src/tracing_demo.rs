// tracing 演示：使用 #[instrument] 宏自动 trace

use tracing::{instrument, info};

#[instrument]
fn greet(name: &str) -> String {
    info!("Greeting");
    format!("Hello, {}!", name)
}

#[instrument]
fn add(a: i32, b: i32) -> i32 {
    info!("Adding");
    a + b
}

fn main() {
    tracing_subscriber::fmt::init();
    println!("{}", greet("World"));
    println!("{}", add(1, 2));
}
