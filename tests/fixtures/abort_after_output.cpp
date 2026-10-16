// Prints the right answer, then aborts (SIGABRT): must still fail.
#include <cstdlib>
#include <iostream>
int main() { std::cout << "5\n" << std::flush; std::abort(); }
