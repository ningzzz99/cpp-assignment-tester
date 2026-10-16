// Demo: compiles and runs, but ignores non-positive values, so the
// negative_values test fails while the others pass.
#include <iostream>

int main() {
    int n = 0;
    std::cin >> n;
    double sum = 0.0;
    for (int i = 0; i < n; ++i) {
        double value = 0.0;
        std::cin >> value;
        if (value > 0) sum += value;  // bug
    }
    std::cout << sum / n << "\n";
    return 0;
}
