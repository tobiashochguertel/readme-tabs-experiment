package main

import "fmt"

func fibonacci(n int) []int {
	result := []int{}
	a, b := 0, 1
	for a < n {
		result = append(result, a)
		a, b = b, a+b
	}
	return result
}

func main() {
	fmt.Println(fibonacci(100))
	// [0 1 1 2 3 5 8 13 21 34 55 89]
}
