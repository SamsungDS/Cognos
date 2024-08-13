#include <iostream>
#include <map>
#include <sstream>
#include "sc_servicer.h"
#include "sc_global.h"
#include "sc_mbox.h"
#include "framework_downstream.h"

extern "C"{
#include "jansson.h"
#include "/opt/stg/mbox_a1.h"
}

using namespace std;

sc_global cxl_global;


//function pointers for the commands
typedef std::string (*CommandFunc)(const std::string&);

/** 
 * @brief tokenize input based on ';' and generate key values.
 * @param input - input string having Cluster ID, Command, Device ID etc.
 * @return tokens unordered map  
*/    
unordered_map<string, string> tokenize(string input){

    char *s = (char *) input.c_str();
    char *tok = strtok(s, ";");
    char key[256], val[256];
    unordered_map <string, string> tokens;
    while (tok != NULL)
    {
        sscanf(tok, "%[a-zA-Z0-9_]=%[/a-zA-Z0-9]", key, val);
        tokens[key] = val;
        tok = strtok(NULL, ";");
    }
    return tokens;}

/** 
 * @brief tokenization helper function which invokes tokenize function.
 * @param input - input string having Cluster ID, Command, Device ID etc.
 * @return tokens unordered map  
*/    
unordered_map<string, string> token_helper(string input){
    unordered_map<string, string> tokens_map = tokenize(input);
    return tokens_map;
}


/**
 * @brief ListDevices - invokes list_devices function of Device Class.
 * @param input string having Cluster ID, Command, FM_ID, FM_Endpoint.
 * @return output CXL devices info in json string.
*/
std::string ListDevices(const std::string& input) {

    string output = input + ";device names=";
    unordered_map<string, string> tokens_map = token_helper(input);
    // Create a buffer to store the JSON data
    std::string buffer;
    size_t bytes_written = cxl_global.list_devices(buffer);
    // Resize the string to the actual size of the JSON data
    buffer.resize(bytes_written);
    output+=buffer;
    return output;
}


/**
 * @brief ListHosts - invokes list_hosts function of Device Class.
 * @param input string having Cluster ID, Command, ID.
 * @return output Hosts list in json string.
*/
std::string ListHosts(const std::string& input) {

    string output = input + ";host names=";
    unordered_map<string, string> tokens_map = token_helper(input);
    // Create a buffer to store the JSON data
    std::string buffer;
    size_t bytes_written = cxl_global.list_hosts(buffer);
    // Reserve the initial buffer size
    buffer.resize(bytes_written);
    output+=buffer;
    return output;
}


/**
 * @brief attach device to host.
 * @param input string having Cluster ID, Command, device_id, host_id & mode.
 * @return output Success/Failure in json string.
*/
std::string AttachMemory(const std::string& input) {

    string output = input + ";AttachMemory=";
    unordered_map<string, string> tokens_map = token_helper(input);
    std::string buffer; 
    //@todo fm_id 203, 204 
    size_t bytes_written = cxl_global.dev_attach(stoull(tokens_map["dev_id"]), stoull(tokens_map["host_id"]), tokens_map["mode"], 203, buffer);
    buffer.resize(bytes_written);
    output+=buffer;
    return output;
}

/**
 * @brief detach device from host.
 * @param input string having Cluster ID, Command, device_id, host_id & mode.
 * @return output Success/Failure in json string.
*/
std::string DetachMemory(const std::string& input) {

    string output = input + ";DetachMemory=";
    unordered_map<string, string> tokens_map = token_helper(input);
    // Create a buffer to store the JSON data
    std::string buffer;
    //@todo fm_id 203, 204
    size_t bytes_written = cxl_global.dev_detach(stoull(tokens_map["dev_id"]), stoull(tokens_map["host_id"]), tokens_map["mode"], 203, buffer);
    // Reserve the initial buffer size
    buffer.resize(bytes_written);
    output+=buffer;
    return output;
}


/**
 * @brief ListHosts - invokes list_hosts function of Device Class.
 * @param input string having Cluster ID, Command, ID.
 * @return output Hosts list in json string.
*/
std::string SetupInfo(const std::string& input) {

    string output = input + ";setup_info=";
    unordered_map<string, string> tokens_map = token_helper(input);
    // Create a buffer to store the JSON data
    std::string buffer;
    size_t bytes_written = cxl_global.fetch_setup_info(buffer);
    // Reserve the initial buffer size
    buffer.resize(bytes_written);
    output+=buffer;
    return output;
}  

/**
 * @brief init function
 * @details This function will be triggered first for any requests from client side.
*/
int init_cxl_plugin(){
    struct StaticPortInfo pinfo;
    mbox_get_static_config(&pinfo);
    return cxl_global.g_create_mbox(&pinfo);
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
    cout << "initialize function called" << endl;

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
    cout << "get_supported_feature_list function called" << endl;
    *feat_id = feature_id::CXL;
    return SVK_STATUS_SUCCESS;
}

/**
 * @brief Check if license is valid
 *
 * Every request needs to validate if license is valid before moving on
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status  is_license_valid(void *) {
    cout << "is_license_valid function called" << endl;
    return SVK_STATUS_FAIL;
}

/**
 * @brief API for feature modules that need to access/initialize a device
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status  configure_device_if_any(void *, svk_device_ctx *, uint64_t length, void *) {
    cout << "configure_device_if_any function called" << endl;
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
    cout << "execute_sync function called" << endl;
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
    std::map<std::string, CommandFunc> fw_hooks {{"ListDevices", ListDevices},{"ListHosts", ListHosts},{"SetupInfo", SetupInfo},{"AttachMemory", AttachMemory},{"DetachMemory", DetachMemory}};

    // Execute the corresponding command function
    try {
        result = fw_hooks.at(commandValue)(input_str);
    } catch (const std::out_of_range&) {
        std::cerr << "Command not found: " << commandValue << std::endl;
        return SVK_STATUS_FAIL;
    } catch (const std::exception& e) {
        std::cerr << "Invalid command: " << e.what() << std::endl;
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
    cout << "execute_async function called" << endl;
    return SVK_STATUS_FAIL;
}

/**
 * @brief Usual cleanup before exit
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status clean_up(void *) {
    cout << "clean_up function called" << endl;
    return SVK_STATUS_FAIL;
}

/**
 * ######################################
 * # END SVK Core Framework Integration #
 * ######################################
 */
