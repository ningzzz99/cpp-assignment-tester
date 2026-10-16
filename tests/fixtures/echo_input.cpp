// Echoes stdin, proving input is delivered per test.
#include <iostream>
#include <string>
int main() { std::string s; while (std::getline(std::cin, s)) std::cout << s << "\n"; return 0; }
