// volatile keeps the compiler from deleting the (otherwise UB) endless loop.
int main() { volatile bool running = true; while (running) {} return 0; }
