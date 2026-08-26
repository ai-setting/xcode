"""简单函数 trace 示例：trace 一个 hello world 风格函数"""


def greet(name: str) -> str:
    """Simple greeting."""
    return f"Hello, {name}!"


def add(a: int, b: int) -> int:
    """Simple addition."""
    return a + b


if __name__ == '__main__':
    print(greet("World"))
    print(add(1, 2))
