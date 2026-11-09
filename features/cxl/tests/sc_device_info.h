#ifndef __SC_DEVICE_INFO
#define __SC_DEVICE_INFO
#include <pybind11/embed.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <map>
#include <regex>
#include <string>
#include <vector>

using namespace std;

namespace py = pybind11;

// Function to replace a specific line
std::string replaceLine(std::string input, std::string pattern,
                        std::string replacement) {
  // Regex to match the whole line: .*pattern.*
  // Using R"()" for raw string literals simplifies escaping
  string p = ".*";
  p += pattern;
  p += ".*";
  std::regex re(p);

  return std::regex_replace(input, re, replacement);
}

// Structure to hold the range
struct Range {
  long long start;
  long long end;
};

// Function to parse hyphenated string "min-max"
bool parseRange(const std::string& str, Range& r) {
  return std::sscanf(str.c_str(), "%llx-%llx", &r.start, &r.end) == 2;
}

// Check if sub is within main
bool isSubrange(const std::string& mainStr, const std::string& subStr) {
  Range mainR, subR;
  if (!parseRange(mainStr, mainR) || !parseRange(subStr, subR)) {
    return false;  // Invalid format
  }
  return (subR.start >= mainR.start && subR.end <= mainR.end);
}

// Data for setup1
// This machine has 1 CMM-H devices and OS as Oracle linux 10
const string lsmem_output_all_setup1 = {
    R"(
    RANGE                                  SIZE  STATE REMOVABLE     BLOCK NODE  ZONES
    0x0000000000000000-0x000000007fffffff    2G online       yes         0    0   None
    0x0000000100000000-0x000000407fffffff  254G online       yes     2-128    0 Normal
    0x0000061f80000000-0x0000065f7fffffff  256G online       yes 3135-3262    1 Normal
    0x0000065f80000000-0x0000085f7fffffff    2T online       yes 3263-4286    2 Normal

    Memory block size:         2G
    Total online memory:     2.5T
    Total offline memory:      0B

)"};

map<string, int> m_range_node_setup1 = {
    {"0000000000000000-000000007fffffff", 0},
    {"0000000100000000-000000407fffffff", 0},
    {"0000061f80000000-0000065f7fffffff", 1},
    {"0000065f80000000-0000085f7fffffff", 2}};

const vector<string> v_bdf_setup1 = {"0000:a4:00.0"};

const vector<string> v_lspci_vvv_s_bdf_grep_Range1_setup1 = {R"(
    Range1: 0000065f80000000-0000085f7fffffff [size=0x20000000000]
)"};

// Data for setup2
// This machine has 4 CMM-H devices and OS as Oracle Linux 9
const string lsmem_output_all_setup2 = {
    R"(
    RANGE                                  SIZE  STATE REMOVABLE     BLOCK NODE  ZONES
0x0000000000000000-0x000000007fffffff    2G online       yes         0    0   None
0x0000000100000000-0x000000407fffffff  254G online       yes     2-128    0 Normal
0x0000004080000000-0x000002407fffffff    2T online       yes  129-1152    2 Normal
0x0000029000000000-0x000004907fffffff    2T online       yes 1312-2336    3 Normal
0x0000061f00000000-0x0000065effffffff  256G online       yes 3134-3261    1 Normal
0x0000065f00000000-0x0000085effffffff    2T online       yes 3262-4285    4 Normal
0x000008af00000000-0x00000aaeffffffff    2T online       yes 4446-5469    5 Normal

Memory block size:         2G
Total online memory:     8.5T
Total offline memory:      0B
)"};
map<string, int> m_range_node_setup2 = {
    {"0000000000000000-000000007fffffff", 0},
    {"0000000100000000-000000407fffffff", 0},
    {"0000004080000000-000002407fffffff", 2},
    {"0000029000000000-000004907fffffff", 3},
    {"0000061f00000000-0000065effffffff", 1},
    {"0000065f00000000-0000085effffffff", 4},
    {"000008af00000000-00000aaeffffffff", 5}};

const vector<string> v_bdf_setup2 = {"0000:27:00.0", "0000:5a:00.0",
                                     "0000:a4:00.0", "0000:c6:00.0"};

const vector<string> v_lspci_vvv_s_bdf_grep_Range1_setup2 = {
    R"(Range1: 0000004080000000-000002407fffffff [size=0x20000000000])",
    R"(Range1: 0000029040000000-000004903fffffff [size=0x20000000000])",
    R"(Range1: 0000065f00000000-0000085effffffff [size=0x20000000000])",
    R"(Range1: 000008af00000000-00000aaeffffffff [size=0x20000000000])"};

// Data for setup3
// This machine has 4 CMM-Ds shown as single NUMA node. OS is Ubuntu24
const string lsmem_output_all_setup3 = {
    R"(
    RANGE                                  SIZE  STATE REMOVABLE   BLOCK NODE  ZONES
0x0000000000000000-0x000000007fffffff    2G online       yes       0    0   None
0x0000000080000000-0x00000000ffffffff    2G online       yes       1    0  DMA32
0x0000000100000000-0x0000003fffffffff  252G online       yes   2-127    0 Normal
0x0000004000000000-0x000000407fffffff    2G online       yes     128    0   None
0x0000004080000000-0x000000fcffffffff  754G online       yes 129-505    1 Normal
0x0000010000000000-0x000001437fffffff  270G online       yes 512-646    1 Normal

Memory block size:         2G
Total online memory:     1.3T
Total offline memory:      0B
)"};

map<string, int> m_range_node_setup3 = {
    {"0000000000000000-000000007fffffff", 0},
    {"0000000080000000-00000000ffffffff", 0},
    {"0000000100000000-0000003fffffffff", 0},
    {"0000004000000000-000000407fffffff", 0},
    {"0000004080000000-000000fcffffffff", 1},
    {"0000010000000000-000001437fffffff", 1}};

const vector<string> v_bdf_setup3 = {"0000:7e:00.0", "0000:7f:00.0",
                                     "0000:fe:00.0", "0000:ff:00.0"};

const vector<string> v_lspci_vvv_s_bdf_grep_Range1_setup3 = {
    R"(Range1: 0000000000000000-0000003fffffffff)",
    R"(Range1: 0000000000000000-0000003fffffffff)",
    R"(Range1: 0000000000000000-0000003fffffffff)",
    R"(Range1: 0000000000000000-0000003fffffffff)"};

#endif
