// Fibonacci sequence
function fibonacci(n) {
  const result = [];
  let [a, b] = [0, 1];
  while (a < n) {
    result.push(a);
    [a, b] = [b, a + b];
  }
  return result;
}

console.log(fibonacci(100));
// [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89]
