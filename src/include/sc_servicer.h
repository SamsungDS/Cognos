#ifndef __CXL_PLUGIN_SC_SERVICER_H__
#define __CXL_PLUGIN_SC_SERVICER_H__


#include <bits/stdc++.h>
#include <cmath>
#include <unordered_map>
#include <string>
#include <functional>
#include "types.h"

std::unordered_map<std::string, std::string> tokenize(std::string input);
		
std::unordered_map<std::string, std::string> token_helper(std::string input);
		
std::string ListDevices(std::string input);
		
std::string ListHosts(std::string input);
		
std::string AttachMemory(std::string input);
		
std::string DetachMemory(std::string input);
		
std::string SetupInfo(std::string input);

std::string get_ip_address(const std::string &filename);

extern "C"{
    int init_cxl_plugin();
}


#endif
