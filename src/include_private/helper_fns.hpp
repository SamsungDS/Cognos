#ifndef __HELPER_FNS_HPP__
#define __HELPER_FNS_HPP__

#include <nlohmann/json.hpp>

int initialize_logger(nlohmann::json logger_config);
int run_command(const uint8_t *buffer, uint64_t len, std::string &output);
int find_node_info(std::string data_type, std::string node_info_script_path,
                   std::string &output);

#endif /*__HELPER_FNS_HPP__*/
