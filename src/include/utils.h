#ifndef __utils__
#define __utils__

#include <iostream>
#include <iostream>
#include <sstream>
#include <fstream>
#include <vector>
#include <string>
#include <map>
#include <unordered_map>

using namespace std;

/**
 * @brief function executes command line/system command through popen
 * @details 
 * @params:
 *  input : command to be executed
 *  output: output of the command in a string vector
 * @return: status of command execution
 */
int execute_command(string,  vector <string>, bool);

#endif