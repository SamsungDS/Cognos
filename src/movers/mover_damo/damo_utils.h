#ifndef __DAMO_UTILS_H__
#define __DAMO_UTILS_H__

#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

using namespace std;

/**
 * @brief function executes command line/system command through popen
 * @details
 * @params:
 *  input : command to be executed
 *  output: output of the command in a string vector
 * @return: status of command execution
 */
string create_config_gen_command(string, string, string, string, string, string);

/**
 * @brief function executes command line/system command through popen
 * @details
 * @params:
 *  input : command to be executed
 *  output: output of the command in a string vector
 * @return: status of command execution
 */
int execute_command(string, vector<string>&, bool);


#endif