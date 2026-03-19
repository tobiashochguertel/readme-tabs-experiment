// Fibonacci sequence
fn fibonacci(n: u64) -> Vec<u64> {
    let mut result = Vec::new();
    let (mut a, mut b) = (0u64, 1u64);
    while a < n {
        result.push(a);
        (a, b) = (b, a + b);
    }
    result
}

fn main() {
    println!("{:?}", fibonacci(100));
    // [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89]
}
