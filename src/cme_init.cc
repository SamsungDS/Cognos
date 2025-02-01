#include <iostream>
#include <sstream>
#include <fstream>
#include <map>
#include <unordered_map>
#include <tuple>
#include <vector>
#include <stdexcept>
#include <functional>
#include <sys/stat.h>
#include <regex>

#include "framework_downstream.h"
#include "tuner.h"
#include "yaml-cpp/yaml.h"

/*
extern "C"{
#include "jansson.h"
}
*/

constexpr char DELIMITER[] = ",";

using namespace std;

//function pointers for the commands
typedef std::string (*CommandFunc)(const std::string&);

//Global tuner object
tuner mt_obj;

/**
 * @brief Start Memory tuner
 * @param command string which includes memory tier params,
 * sla params, application params
 * @return status code of tuner start: 0 = success
*/
std::string StartTuning(const std::string& input) {
    unordered_map<string, string> tokens_map = token_helper(input);
    int ret;
    ret = mt_obj.tuner_start(tokens_map, PAGE_MOVER_DAMO);
    return to_string(ret);
}

/**
 * @brief Stop Memory tuner
 * @param command string
 * @return status code of tuner stop: 0 = success
*/
std::string StopTuning(const std::string& input) {
    unordered_map<string, string> tokens_map = token_helper(input);
    pair <string, unsigned long> tuner_context_key = make_pair(tokens_map["application"], stoul(tokens_map["application_id"]));
    int ret;
    ret = mt_obj.tuner_stop(tuner_context_key);
    return to_string(ret);
}

/**
@brief Validate the format of an IPv4 address
@param ip_address - the IP address to validate
@return true if the IP address is valid, false otherwise
 */
bool is_valid_ip(const std::string &ip_address) {
    // Trim whitespace 
    std::string trimmed_ip = ip_address;
    trimmed_ip.erase(0, trimmed_ip.find_first_not_of(" \t\n\r"));
    trimmed_ip.erase(trimmed_ip.find_last_not_of(" \t\n\r") + 1);
    // Regular expression for a valid IPv4 address
    const std::regex ip_pattern( \
	"(^(1[0-9]{0,2}|2[0-4][0-9]|25[0-5]|[1-9][0-9]?)\\." \
	"(25[0-5]|2[0-4][0-9]|[0-1]?[0-9][0-9]?)\\." \
        "(25[0-5]|2[0-4][0-9]|[0-1]?[0-9][0-9]?)\\." \
        "(25[0-5]|2[0-4][0-9]|[0-1]?[0-9][0-9]?)$)"
    );

    return std::regex_match(trimmed_ip, ip_pattern);
}

/**
 * @brief init tm functionality
 * @details As cxl cleanup is not called, 
 * deleting left over config files explicitly.
*/
void tm_init()
{
    /*clean up cgroup
    TODO: Cgroup delete needs yaml parsing
    ret = cgroup_delete();
    */
    damo_global_config_cleanup();
}

/**
 * @brief init function
 * @details This function will be triggered first for any requests from client side.
*/
int init_cxl_plugin() {
    std::cout << "invoked init_cxl_plugin" << std::endl;
    tm_init();

    return 0;
}

/**
 * ########################################
 * # Start SVK Core Framework Integration #
 * ########################################
 */


/**
 * @brief Initialize individual feature module
 *
 * This will be called when individual feature module will be loaded by
 * framework.
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status  initialize(void *) {
    std::cout << "initialize function called" << std::endl;

    if (init_cxl_plugin()==0){
	return SVK_STATUS_SUCCESS;
    }else{
        return SVK_STATUS_FAIL;
    }
}

/*
 * Feature modules set feature_id to the *feat_id pointer if
 * it isn't set already.
 * SVK command framework will call this function to get the feature names
 * this feature module will support.
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status  get_supported_feature_list(feature_id *feat_id, char *) {
    std::cout << "get_supported_feature_list function called" << std::endl;
    *feat_id = feature_id::CME;
    return SVK_STATUS_SUCCESS;
}

/**
 * @brief Check if license is valid
 *
 * Every request needs to validate if license is valid before moving on
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status  is_license_valid(void *) {
    std::cout << "is_license_valid function called" << std::endl;
    return SVK_STATUS_FAIL;
}

/**
 * @brief API for feature modules that need to access/initialize a device
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status  configure_device_if_any(void *, svk_device_ctx *, uint64_t length, void *) {
    std::cout << "configure_device_if_any function called" << std::endl;
    return SVK_STATUS_FAIL;
}

/**
 * @brief Exact feature execution logic will be implemented here
 *
 * @param pass_thru svk passthrough for command info communication from top
 * level
 * @param input     input buffer struct
 * @param result    output buffer struct
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status execute_sync(svk_pass_thru_cmd *, svk_input *input, svk_output *output) {
    std::cout << "execute_sync function called" << std::endl;
    std::string input_str(reinterpret_cast<char*>(input->input_buffer), input->len);
    std::string result;

    std::string commandValue;
    std::istringstream ss(input_str);
    std::string token;

    while (std::getline(ss, token, ';')) {
        const std::string prefix = "command=";
        if (token.find(prefix) == 0) {
            commandValue = token.substr(prefix.length());
            break;
        }
    }

    //@to-do - resolve gcov code coverage for multilines. 
    // Map of command strings to their corresponding functions
    std::map<std::string, CommandFunc> fw_hooks {
      {"StartTuning", StartTuning},
      {"StopTuning", StopTuning}
    };

    // Execute the corresponding command function
    try {
        result = fw_hooks.at(commandValue)(input_str);
    } catch (const std::out_of_range&) {
        std::cerr << "Command not found: " << commandValue << std::endl;
        return SVK_STATUS_FAIL;
    } 

    output->output_buffer = reinterpret_cast<uint8_t*>(strdup(result.c_str()));
    output->len = result.size();
    output->status = SVK_STATUS_SUCCESS;
    return SVK_STATUS_SUCCESS;
}

/**
 * @brief Feature module async execute implementation.
 *
 * @param pass_thru       svk passthrough for command info communication from
 * top level
 * @param input           input buffer struct
 * @param postprocess_fn  struct containing pointers for async IO, such as
 * callback, IO identifier, and output buffer
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status execute_async(svk_pass_thru_cmd *, svk_postprocess_fn *) {
    std::cout << "execute_async function called" << std::endl;
    return SVK_STATUS_FAIL;
}

/**
 * @brief Usual cleanup before exit
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status clean_up(void *) {
    std::cout << "clean_up function called" << std::endl;
    return SVK_STATUS_FAIL;
}

/**
 * ######################################
 * # END SVK Core Framework Integration #
 * ######################################
 */
