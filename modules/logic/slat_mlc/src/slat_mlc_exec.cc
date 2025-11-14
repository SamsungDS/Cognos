#include <iostream>
#include <regex>
#include <sstream>
#include <string>

#include "slat_benchmark.hpp"
#include "slat_run_bin.hpp"

/**
 * The output of mlc --idle_latency output is of the format
 * root@msl-ssg-srf04:~#
/usr/local/svk/feature_modules/slat/logic_modules/mlclogic/bin/mlc
--idle_latency -b200m  -c2 -j2 Intel(R) Memory Latency Checker - v3.11b Command
line parameters: --idle_latency -b200m -c2 -j2

Using buffer size of 200.000MiB
Each iteration took 1782.2 base frequency clocks (      742.6   ns)

 */
std::string parseMLCIdleLatencyOutput(const std::string& cmd_output) {
  std::istringstream outstream(cmd_output);
  std::string line;
  std::string status = "status=failed";

  std::regex idle_lat_re("Each iteration.*\\(([^)]+)\\)");
  std::smatch idle_lat_match;
  while (std::getline(outstream, line)) {
    if (std::regex_search(line, idle_lat_match, idle_lat_re)) {
      std::istringstream restream(idle_lat_match[1].str());
      std::string lat_res;
      std::string lat_precision;
      restream >> lat_res;
      restream >> lat_precision;

      double latency_result = std::atof(lat_res.c_str());

      if (lat_precision != "ns") {
        std::cout << "unknown latency precision detected [" + lat_precision +
                         "]" + lat_res
                  << std::endl;
        return status;
      }
      status = "status=success;avgLatencyns=" + std::to_string(latency_result);
      return status;
    }
  }
  return status;
}

/**
 * The output of mlc command with latency_matrix will be of the form. For the
 * given numa, parse for the value under the numa node's column of the first
 * line reported from numa node 0
 *
 * root@msl-ssg-srf04:~#
 /usr/local/svk/feature_modules/slat/logic_modules/mlclogic/bin/mlc
 --latency_matrix
 * Intel(R) Memory Latency Checker - v3.11b
 * Command line parameters: --latency_matrix

 * Using buffer size of 200.000MiB
 * Measuring idle latencies for sequential access (in ns)...
 *               Numa node
 * Numa node            0       1       2       3
 *      0         122.9   421.0   781.4   809.8
 *      1         371.5   151.6   841.8   782.2
 *
 */
std::string parseMLCLatencyMatrixOutput(int numa_node,
                                        const std::string& cmd_output) {
  std::istringstream outstream(cmd_output);
  std::string line;
  std::string status = "status=failed";

  // Use the regex to match the line starting with spaces and 0
  std::regex pattern(R"(^\s*0\s+(.*))");
  std::smatch match;
  int column_num = numa_node + 1;
  bool found = false;

  while (std::getline(outstream, line)) {
    if (std::regex_search(line, match, pattern)) {
      // Line matched. Break into the words and find the column number
      // which is numa_node + 1 and convert to double
      std::istringstream iss(line);
      std::string word;
      int count = 0;
      while (iss >> word) {
        count++;
        if (count == column_num) {
          double latency_result = std::stod(word);
          status =
              "status=success;avgLatencyns=" + std::to_string(latency_result);
          found = true;
          break;
        }
      }
      if (!found) {
        std::cout << "Not enough data found in the output for numa "
                  << numa_node << std::endl;
      }
    }
  }
  return status;
}

std::string runMlc(std::string testType, argOpts args, std::string bin_path) {
  std::string cmd_args;
  exe_ret_info rinfo;
  int numa_node = -1;

  cmd_args += "--";
  cmd_args += testType;
  auto it = args.find("numa_node");
  if (it != args.end()) {
    numa_node = stoi(it->second);
  }

  if (testType == "idle_latency") {
    // Run the mlc command with buffer size of 200MB and time of 10sec
    cmd_args += " -b200 -t10";

    // -j initialize memory from numa node #n
    cmd_args += " -j";
    cmd_args += std::to_string(numa_node);

    // -c affinitize the latency measurement thread to core #n
    cmd_args += " -c";
    cmd_args += std::to_string(numa_node);
  }

  rinfo = runExecutable(bin_path, cmd_args);

  if (rinfo.rc != 0) {
    rinfo.output = "status=failed";
    return rinfo.output;
  }

  if (testType == "idle_latency") {
    rinfo.output = parseMLCIdleLatencyOutput(rinfo.output);
  } else if (testType == "latency_matrix") {
    rinfo.output = parseMLCLatencyMatrixOutput(numa_node, rinfo.output);
  } else {
    rinfo.output = "status=failed";
  }
  // TODO: standardize output
  return rinfo.output;
}
