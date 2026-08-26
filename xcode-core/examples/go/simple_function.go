// Package main 简单函数 trace 示例
package main

import "fmt"

func greet(name string) string {
	return fmt.Sprintf("Hello, %s!", name)
}

func add(a, b int) int {
	return a + b
}

func main() {
	fmt.Println(greet("World"))
	fmt.Println(add(1, 2))
}
