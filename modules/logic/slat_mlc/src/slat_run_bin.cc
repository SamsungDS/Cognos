#include "slat_run_bin.hpp"

#include <boost/process.hpp>
#include <iostream>
#include <string>

namespace bp = boost::process;

exe_ret_info runExecutable(std::string binary, std::string arg_str) {
  exe_ret_info return_info;

  return_info.output = "";

  bp::ipstream out;
  bp::ipstream err;

  bp::child c(binary, arg_str, bp::std_out > out, bp::std_err > err);

  std::string line;
  while (c.running() && std::getline(out, line)) {
    return_info.output += line;
    return_info.output += "\n";
  }

  c.wait();

  std::cout << "--------------ERR---------------------" << std::endl;
  std::string print_line;
  while (err && std::getline(err, print_line) && !print_line.empty()) {
    std::cout << print_line << std::endl;
  }

  std::cout << "--------------OUT---------------------" << std::endl;
  std::cout << return_info.output << std::endl;

  return_info.rc = c.exit_code();

  return return_info;
}