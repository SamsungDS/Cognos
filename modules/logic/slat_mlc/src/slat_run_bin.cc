#include "slat_run_bin.hpp"

#include <boost/filesystem.hpp>
#include <boost/process.hpp>
#include <iostream>
#include <string>

namespace bp = boost::process;

exe_ret_info runExecutable(const std::string &binary,
                           const std::string &arg_str) {
  exe_ret_info return_info;

  return_info.output = "";

  bp::ipstream out;
  bp::ipstream err;
  std::string cmd_str = binary + " " + arg_str;

  boost::filesystem::path p(binary);
  if (boost::filesystem::exists(p) == false) {
    return_info.rc = -1;
    return return_info;
  }

  return_info.rc = bp::system(cmd_str, bp::std_out > out, bp::std_err > err);

  std::string line;
  while (std::getline(out, line)) {
    return_info.output += line;
    return_info.output += "\n";
  }

  std::cout << "--------------ERR---------------------" << std::endl;
  std::string print_line;
  while (err && std::getline(err, print_line) && !print_line.empty()) {
    std::cout << print_line << std::endl;
  }

  std::cout << "--------------OUT---------------------" << std::endl;
  std::cout << return_info.output << std::endl;

  return return_info;
}