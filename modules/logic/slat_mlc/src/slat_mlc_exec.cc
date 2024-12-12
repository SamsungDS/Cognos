#include <iostream>
#include <regex>
#include <sstream>
#include <string>

#include "slat_benchmark.hpp"
#include "slat_run_bin.hpp"

std::string runMlc(std::string testType, argOpts args, std::string bin_path) {
  std::string cmd_args;
  exe_ret_info rinfo;

  cmd_args += "--";
  cmd_args += testType;

  auto it = args.find("numa_node");
  if (it != args.end()) {
    auto numa_node = stoi(it->second);

    cmd_args += " -j";
    cmd_args += std::to_string(numa_node);
  }

  rinfo = runExecutable(bin_path, cmd_args);

  if (rinfo.rc != 0) {
    rinfo.output = "status=failed";
  }

  std::istringstream outstream(rinfo.output);
  std::string line;

  if (testType == "idle_latency") {
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
          return "status=failed";
        }
        rinfo.output =
            "status=success;avgLatencyns=" + std::to_string(latency_result);
      }
    }
  } else {
    std::cout << "Invalid test type " + testType << std::endl;
    rinfo.output = "status=failed";
  }
  // TODO: standardize output
  return rinfo.output;
}