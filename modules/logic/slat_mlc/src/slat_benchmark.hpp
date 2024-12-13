#ifndef SLAT_BENCHMARK_HPP
#define SLAT_BENCHMARK_HPP

#include <map>
#include <string>

#include "logic_interface/svk_logic_interface.h"

using argOpts = std::map<std::string, std::string>;
std::string runMlc(std::string testType, argOpts args, std::string bin_path);
svk_status configure_slat_mlc_logic(const std::string slat_logic_conf_file);
svk_status execute_mlc_logic_sync(svk_logic_cmd *cmd, svk_logic_input *input,
                                  svk_logic_output *output);
#endif  // SLAT_BENCHMARK_HPP
