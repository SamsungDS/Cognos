#ifndef __utils__
#define __utils__

#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <unordered_map>
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
int execute_command(string, vector<string>, bool);

#endif