// class_methods.go - 结构体方法 trace 示例
package main

import "fmt"

type Calculator struct {
	Name string
}

// Calculator.Add 方法
func (c *Calculator) Add(a, b int) int {
	return a + b
}

// Calculator.Multiply 方法
func (c *Calculator) Multiply(a, b int) int {
	return a * b
}

// Calculator.Chain 串联多个方法
func (c *Calculator) Chain(x int) int {
	r1 := c.Add(x, 1)
	r2 := c.Multiply(r1, 2)
	return r2
}

func main() {
	calc := &Calculator{Name: "test"}
	result := calc.Chain(5)
	fmt.Printf("Result: %d\n", result)
}
