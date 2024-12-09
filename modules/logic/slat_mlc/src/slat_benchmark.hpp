#ifndef SLAT_BENCHMARK_HPP
#define SLAT_BENCHMARK_HPP

#include <map>
#include <string>

using argOpts = std::map<std::string, std::string>;
std::string runMlc(std::string testType, argOpts args, std::string bin_path);

#endif  // SLAT_BENCHMARK_HPP
