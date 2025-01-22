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

#include "sc_fm.h"
#include "sc_servicer.h"
#include "sc_global.h"
#include "sc_mbox.h"
#include "framework_downstream.h"
#include "sc_cmmd.h"
#include "sc_cmmh.h"
#include "sc_cmmb.h"
#include "tuner.h"
#include "yaml-cpp/yaml.h"


extern "C"{
#include "jansson.h"
#include "mbox_a1.h"
}

#define CXL_CONF_FILE "cxl.conf"
#define INPUT_CONF_FILE "input.conf"
constexpr char DELIMITER[] = ",";

using namespace std;

sc_global cxl_global;

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
 * @brief get the value of "ip_address" from the JSON file
 * @param filename - switch config file having ip_address
 * @return ip_address
*/
std::string get_ip_address(const std::string &filename) {
    json_error_t error;
    // Load the JSON file
    json_t *root = json_load_file(filename.c_str(), 0, &error);
    if (!root) {
        std::cerr << "Error loading JSON file: " << error.text << std::endl;
        return "";
    }
    // Get the "switch" object from the JSON
    json_t *switch_obj = json_object_get(root, "switch");
    if (!switch_obj || !json_is_object(switch_obj)) {
        std::cerr << "Error: 'Switch' key not found or not an object" << std::endl;
        json_decref(root);
        return "";
    }
    // Get the "ip_address" value from the "switch" object
    json_t *ip_address = json_object_get(switch_obj, "ip_address");
    if (!ip_address || !json_is_string(ip_address)) {
        std::cerr << "Error: 'ip_address' key not found or not a string" << std::endl;
        json_decref(root);
        return "";
    }
    // Extract the IP address value
    std::string ip_value = json_string_value(ip_address);
    // Validate the IP address format
    if (!is_valid_ip(ip_value)) {
        std::cerr << "Error: Invalid IP address format: " << ip_value << std::endl;
        json_decref(root);
        return "";
    }
    // Clean up
    json_decref(root);
    return ip_value;
}

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

    string output = "";
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

    string output = "";
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

    string output = "";
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

    string output = "";
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
 * @brief provide direct attached host or switch setup such as hosts, devices, endpoints.
 * @param input string having Cluster ID, Command, ID.
 * @return setup details as string.
*/
std::string SetupInfo(const std::string& input) {
    std::string output;
    std::string buffer;
    std::unordered_map<std::string, std::string> tokens_map = token_helper(input);
    // Retrieve all sc_id keys from cxl_global
    std::vector<sc_id> fm_keys = cxl_global.get_fm_keys();
    output += "[";
    // Counter to track the number of FabricManagers parsed
    uint32_t fm_count = 0;
    // Iterate over each key, retrieve the FabricManager, and call setup_info
    for (auto& id : fm_keys) {
        FabricManager* manager = cxl_global.find_fm(id);
        if (manager) {
            std::cout << "Invoke Direct attached host setup_info" << std::endl;
            size_t bytes_written = manager->setup_info(buffer);
            buffer.resize(bytes_written);
            // Add a delimiter only if this is not the first FabricManager
            if (fm_count > 0) {
                output += std::string(DELIMITER);
            }
            output += buffer;
            ++fm_count;
        }
    }
    // Close the JSON array
    output += "]";
    if (fm_count == 0) {
        std::cerr << "No FabricManager found " << std::endl;
    }
    return output;
}


void create_dev_cmmd(json_t* config) {
    // Allocate DevCMMD on the heap
    DevCMMD* manager = new DevCMMD(config);
    cxl_global.add_fm(manager->get_fmid(), *manager);
    std::cout << "Added DevCMMD to map." << std::endl;
}


void create_dev_cmmh(json_t* config) {
    // Allocate DevCMMH on the heap
    DevCMMH* manager = new DevCMMH(config);
    cxl_global.add_fm(manager->get_fmid(), *manager);
    std::cout << "Added DevCMMH to map." << std::endl;
}


void create_dev_cmmb(json_t* config) {
    // Allocate DevCMMB on the heap
    DevCMMB* manager = new DevCMMB(config);
    cxl_global.add_fm(manager->get_fmid(), *manager);
    std::cout << "Added DevCMMB to map." << std::endl;
}


const std::unordered_map<std::string, std::function<void(json_t*)>> factory_map = {
    {"FM_DIRECT_CMMD", create_dev_cmmd},
    {"FM_DIRECT_CMMH", create_dev_cmmh},
    {"FM_REMOTE_CMMB", create_dev_cmmb}
};


/**
 * Helper function to create cmmb fabric manager map dynamically
 */
json_t* parse_input_config(std::string& buffer) {
    size_t bytes_written = cxl_global.fetch_setup_info(buffer);
    buffer.resize(bytes_written);

    json_error_t error;
    json_t* parsed_buffer = json_loads(buffer.c_str(), 0, &error);
    json_t* hosts = json_object_get(parsed_buffer, "Hosts");
    json_t* devices = json_object_get(parsed_buffer, "Devices");
    if (!hosts || !devices) {
        std::cerr << "missing 'Hosts' or 'Devices' in parsed JSON." << std::endl;
        json_decref(parsed_buffer);
        return nullptr;
    }
    std::cout<< "Constructing CMMB fabric manager entry." << std::endl;
    json_t* cmmb_fm = json_object();
    json_object_set_new(cmmb_fm, "id", json_integer(4004));
    json_object_set_new(cmmb_fm, "type", json_string("FM_REMOTE_CMMB"));
    json_object_set(cmmb_fm, "Hosts", hosts);
    json_object_set(cmmb_fm, "Devices", devices);
    std::cout<<"CMMB fabric manager entry constructed successfully."<<std::endl;
    json_decref(parsed_buffer);
    return cmmb_fm;
}


/**
 * @brief function would take each fabric_manager entry, check for a valid type
 *        and handle unknown types
 */
int process_fabric_manager(json_t* fabric_manager) {
    json_t* type_json = json_object_get(fabric_manager, "type");
    if (!json_is_string(type_json)) {
        std::cerr << "Missing or invalid 'type' field in fabric_manager" << std::endl;
        return 1; 
    }
    std::string type_str = json_string_value(type_json);
    auto it = factory_map.find(type_str);
    if (it != factory_map.end()) {
	// Call factory function    
        it->second(fabric_manager); 
    } else {
        std::cerr << "Unknown fabric_manager type: " << type_str << std::endl;
        return 2; 
    }
    return 0; 
}


bool is_file_empty_or_missing(const std::string& file_path) {
    struct stat file_stat;
    // Check if the file exists
    if (stat(file_path.c_str(), &file_stat) != 0) {
        std::cerr << "Error: Cannot access file: " << file_path << std::endl;
        return true;
    }
    // Check if the file is empty
    if (file_stat.st_size == 0) {
        std::cerr << "Error: File is empty: " << file_path << std::endl;
        return true;
    }
    return false;
}

/**
 * @brief  Function to load the JSON config file with path availability check, 
 *         error handling and return the json_t object 
*/
json_t* direct_config(const std::string& input_config) {
    json_error_t error;
    json_t* config_json = json_load_file(input_config.c_str(), 0, &error);
    if (!config_json) {
        std::cerr << "Error loading JSON file: " << error.text << std::endl;
    }
    return config_json;
}


/**
 * @brief  load and validate the JSON structure, ensuring the file is correctly parsed 
 *         and contains a fabric_managers array
 */
json_t* load_json_config(const std::string& config_path) {
    json_t* root = direct_config(config_path);
    if (!root || !json_is_object(root)) {
        std::cerr << "Failed to load or parse configuration file: " << config_path << std::endl;
        return nullptr;
    }
    json_t* fabric_managers = json_object_get(root, "fabric_managers");
    if (!json_is_array(fabric_managers)) {
        std::cerr << "Invalid or missing 'fabric_managers' array in configuration" << std::endl;
        json_decref(root);
        return nullptr;
    }
    return root;
}

int cmmb_a1_init() {
    struct StaticPortInfo pinfo;
    std::string ip_address = get_ip_address(CXL_CONF_FILE);
    set_ip(ip_address.c_str());
    init();
    mbox_get_static_config(&pinfo);
    if (int mret = cxl_global.g_create_mbox(&pinfo); mret != 0) {
        std::cout << "Error creating memory box: " << std::to_string(mret) << std::endl;
        return mret;
    }
    return 0;
}


void fm_init() {

    // Check if the input file is empty or missing
    if (is_file_empty_or_missing(INPUT_CONF_FILE)) {
        return;
    }

    json_t* root = load_json_config(INPUT_CONF_FILE);
    if (!root) {
        std::cout << "Error loading JSON configuration from " << INPUT_CONF_FILE << std::endl;
	return;
    }
    std::cout << "Extracting fabric_managers array..." << std::endl;
    json_t* fabric_managers = json_object_get(root, "fabric_managers");
    std::string buffer;
    json_t* cmmb_fm = parse_input_config(buffer);
    if (cmmb_fm) {
        std::cout << "Adding CMMB fabric manager to fabric_managers array." << std::endl;
        json_array_append_new(fabric_managers, cmmb_fm);
    } else {
        std::cerr << "CMMB fabric manager is null; skipping addition to fabric_managers array." << std::endl;
    }

    // Process each fabric manager in the array
    size_t index;
    json_t* fabric_manager;
    json_array_foreach(fabric_managers, index, fabric_manager) {
        if (process_fabric_manager(fabric_manager) != 0) {
            // Skip if there's an error processing
            continue;
        }
    }
    json_decref(root);
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
    int mret = cmmb_a1_init();
    fm_init();
    tm_init();

    return mret; 
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
    std::map<std::string, CommandFunc> fw_hooks {{"ListDevices", ListDevices},{"ListHosts", ListHosts},{"SetupInfo", SetupInfo},{"AttachMemory", AttachMemory},{"DetachMemory", DetachMemory}, {"StartTuning", StartTuning}, {"StopTuning", StopTuning}};

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
