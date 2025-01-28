#ifndef __DAMO_UTILS_H__
#define __DAMO_UTILS_H__

#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

const std::string SVK_CXL_PATH = "/etc/svk/";
const std::string PM_DAMO_PATH = "/usr/local/bin/damo";
const std::string PM_DAMO_PYTHON3_PATH = "/usr/bin/python3";
const std::string PM_DAMO_CONFIG_GEN_SCRIPT = "tm_gen_config.py";

using namespace std;

/**
 * @brief function executes command line/system command through popen
 * @details
 * @params:
 *  input : command to be executed
 *  output: output of the command in a string vector
 * @return: status of command execution
 */
string create_config_gen_command(string, string, string, string, string,
                                 string);

#endif