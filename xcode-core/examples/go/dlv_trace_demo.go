// dlv_trace_demo.go - Delve trace demo
//
// 使用：
//   go build -o /tmp/dlv_demo dlv_trace_demo.go
//   dlv trace --output /tmp/trace.txt --regex 'main\.' /tmp/dlv_demo
//
package main

import "fmt"

type Calculator struct {
	Name string
}

func (c *Calculator) Add(a, b int) int {
	return a + b
}

func main() {
	calc := &Calculator{Name: "test"}
	result := calc.Add(1, 2)
	fmt.Println(result)
}
