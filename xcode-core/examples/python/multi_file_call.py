"""
跨文件调用链 trace 示例

项目结构：
- multi_file_call.py（这个文件 - 入口）
- module_a.py
- module_b.py

运行后 trace 会显示完整调用链：
  main()
    → process_a()      [module_a.py:5]
    → process_b()      [module_b.py:5]

每个函数都会显示定义位置 + 调用方位置。
"""

from module_a import process_a
from module_b import process_b


def main():
    """Main entry."""
    result_a = process_a(input_data="hello")
    result_b = process_b(input_data="world")
    return result_a + result_b


if __name__ == '__main__':
    main()
