#include <iostream>
#include <string>

int main(int argc, char **argv) {
  std::cout << argc << std::endl;
  if (argc > 1) {
    if (std::string(argv[1]) == "--latency_matrix") {
      std::string message =
          "\
 Intel(R) Memory Latency Checker - v3.11b\n\
 Command line parameters: --latency_matrix\n\
 \n\
 Using buffer size of 200.000MiB\n\
 Measuring idle latencies for sequential access (in ns)...\n\
               Numa node\n\
 Numa node            0       1       2       3\n\
      0         122.9   421.0   781.4   809.8\n\
      1         371.5   151.6   841.8   782.2";
      std::cout << message << std::endl;
    }
  }

  return 0;
}