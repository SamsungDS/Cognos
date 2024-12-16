#ifndef SLAT_RUN_BIN_HPP
#define SLAT_RUN_BIN_HPP

#include <iostream>

struct exe_ret_info_s {
  int rc;
  std::string output;
};

using exe_ret_info = struct exe_ret_info_s;

exe_ret_info runExecutable(const std::string &binary,
                           const std::string &arg_str);

#endif  // SLAT_RUN_BIN_HPP
