"""类方法 trace 示例：trace 类的方法 + 调用方位置"""


class Calculator:
    """A simple calculator class."""

    def add(self, a: int, b: int) -> int:
        return a + b

    def multiply(self, a: int, b: int) -> int:
        return a * b

    def chain(self, x: int) -> int:
        # 调用方位置：第 25 行
        result = self.add(x, 1)
        # 调用方位置：第 27 行
        result = self.multiply(result, 2)
        return result


if __name__ == '__main__':
    calc = Calculator()
    # 调用方位置：第 34 行
    result = calc.chain(5)
    print(f"Result: {result}")
