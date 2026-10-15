// Reads n, then n numbers, and prints their average.
#include <iostream>
#include <vector>

int main() {
    int n = 0;
    if (!(std::cin >> n) || n <= 0) {
        std::cerr << "expected a positive count\n";
        return 1;
    }
    double sum = 0.0;
    for (int i = 0; i < n; ++i) {
        double value = 0.0;
        if (!(std::cin >> value)) {
            std::cerr << "expected " << n << " numbers\n";
            return 1;
        }
        sum += value;
    }
    std::cout << sum / n << "\n";
    return 0;
}
