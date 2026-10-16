#include <cstdlib>
#include <iostream>
int main() { std::cout << (std::getenv("CPPGRADER_SECRET_PROBE") ? "leaked" : "clean") << "\n"; return 0; }
