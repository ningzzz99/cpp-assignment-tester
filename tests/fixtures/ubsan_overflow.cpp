// Prints the expected output, but has signed-integer-overflow undefined behaviour.
#include <climits>
#include <iostream>
int main(int argc, char**) {
    int x = INT_MAX;
    x += argc;
    std::cout << "ok\n";
    return x == 0;
}
