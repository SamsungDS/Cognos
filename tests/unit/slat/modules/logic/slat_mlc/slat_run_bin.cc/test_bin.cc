#include <iostream>
#include <string>

int main(int argc, char **argv) {
  std::cout << argc << std::endl;
  for (int i = 0; i < argc; i++) {
    std::cout << std::string(argv[i]) << std::endl;
    std::cerr << "test print error stream" << std::endl;
    std::cout << "Each iteration ( 20 ms)"
              << std::endl;  // Simulate MLC result parse failure
  }
  return 0;
}