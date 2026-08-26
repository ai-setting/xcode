// 结构体方法 trace 示例

struct Calculator {
    name: String,
}

impl Calculator {
    fn add(&self, a: i32, b: i32) -> i32 {
        a + b
    }

    fn multiply(&self, a: i32, b: i32) -> i32 {
        a * b
    }

    fn chain(&self, x: i32) -> i32 {
        let r1 = self.add(x, 1);
        let r2 = self.multiply(r1, 2);
        r2
    }
}

fn main() {
    let calc = Calculator {
        name: "test".to_string(),
    };
    let result = calc.chain(5);
    println!("Result: {}", result);
}
