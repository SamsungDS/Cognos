#ifndef __cme_utils__
#define __cme_utils__

#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>
#include <iostream>
#include <map>
#include <stdexcept>
#include <tuple>
#include <dlfcn.h>
#include <dirent.h>
#include <errno.h>
#include <sys/inotify.h>
#include <sys/stat.h>
#include <thread>
#include <chrono>
#include <cstdio>
#include "cme_context.h"

using namespace std;

/**
 * @brief struct to add hash function for a pair
 * @details When pair is used in an unordered_map, there is no
 * 	    default hash function, so we need to define one.
 *
 * Example:
 * 	unordered_map<pair<std::string, unsigned long>, cme_context*, pair_hash> cme_contexts_list;
*/
struct pair_hash
{
  template <class T1, class T2>
  std::size_t
  operator() (const std::pair<T1, T2> &p) const
  {
    auto h1 = std::hash<T1>{}(p.first);
    auto h2 = std::hash<T2>{}(p.second);
    return h1 ^ h2;
  }
};

/**
 * @brief function executes command line/system command through popen
 * @details
 * @params:
 *  input : command to be executed
 *  output: output of the command in a string vector
 * @return: status of command execution
 */
bool isDirectory(std::string);

/**
 * @brief tokenize input based on ';' and generate key values.
 * @param input - input string having Cluster ID, Command, Device ID etc.
 * @return tokens unordered map
 */
unordered_map<string, string> tokenize (string);

/**
 * @brief tokenization helper function which invokes tokenize function.
 * @param input - input string having Cluster ID, Command, Device ID etc.
 * @return tokens unordered map
 */
unordered_map<string, string> token_helper (string);

/**
 * @brief parse json input command string and populated token map
 * @param command string
 *        map to update command tokens
 * @return bool : true if incoming command is a valid json string
 *                false otherwise
*/
bool command_parser_json(const std::string &, unordered_map<std::string, std::string> &);

/**
 * @brief function executes command line/system command through popen
 * @details
 * @params:
 *  input : command to be executed
 *  output: output of the command in a string vector
 * @return: status of command execution
 */
int execute_command(const std::string &, vector<string>&, bool);

long get_invalid_pid(void);

bool pid_exists(long pid);

const long DUMMY_PID = -1000;
const std::string DUMMY_PROCESS = "DUMMY_PROCESS";

bool is_valid_numa_node(int);

std::string getCurrentTimestamp(void);

/**
 * @brief function executes numastat and returns the output string
 * @details
 * @params:
 *  numa_node : NUMA node to check memory used for
  * @return: output of the command in a string vector
 */
long long process_numastat_light(int numa_node);

#endif
