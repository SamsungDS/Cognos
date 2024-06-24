#include "sc_servicer.h"
#include "sc_global.h"
#include "sc_mbox.h"

extern "C"{
#include "jansson.h"
#include "/opt/stg/mbox_a1.h"
}

using namespace std;

sc_global cxl_global;

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
string ListDevices(string input) {

    string output = input + ";device names=";
    unordered_map<string, string> tokens_map = token_helper(input);
    const size_t SIZE_B = 5120;
    // Create a buffer to store the JSON data
    std::string buffer;
    // Reserve the initial buffer size
    buffer.resize(SIZE_B);
    size_t bytes_written = cxl_global.list_devices(buffer,SIZE_B);
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
string ListHosts(string input) {

    string output = input + ";host names=";
    unordered_map<string, string> tokens_map = token_helper(input);
    const size_t SIZE_B = 5120;
    // Create a buffer to store the JSON data
    std::string buffer;
    // Reserve the initial buffer size
    buffer.resize(SIZE_B);
    size_t bytes_written = cxl_global.list_hosts(buffer,SIZE_B);
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
string AttachMemory(string input) {

    string output = input + ";AttachMemory=";
    unordered_map<string, string> tokens_map = token_helper(input);
    const size_t SIZE_B = 5120;
    std::string buffer; 
    // Reserve the initial buffer size
    buffer.resize(SIZE_B);
    //@todo fm_id 203, 204 
    size_t bytes_written = cxl_global.dev_attach(stoull(tokens_map["dev_id"]), stoull(tokens_map["host_id"]), tokens_map["mode"], 203, buffer,SIZE_B);
    buffer.resize(bytes_written);
    output+=buffer;
    return output;
}

/**
 * @brief detach device from host.
 * @param input string having Cluster ID, Command, device_id, host_id & mode.
 * @return output Success/Failure in json string.
*/
string DetachMemory(string input) {

    string output = input + ";DetachMemory=";
    unordered_map<string, string> tokens_map = token_helper(input);
    const size_t SIZE_B = 5120;
    // Create a buffer to store the JSON data
    std::string buffer;
    // Reserve the initial buffer size
    buffer.resize(SIZE_B);
    //@todo fm_id 203, 204
    size_t bytes_written = cxl_global.dev_detach(stoull(tokens_map["dev_id"]), stoull(tokens_map["host_id"]), tokens_map["mode"], 203, buffer,SIZE_B);
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
string SetupInfo(string input) {

    string output = input + ";setup_info=";
    unordered_map<string, string> tokens_map = token_helper(input);
    const size_t SIZE_B = 5120;
    // Create a buffer to store the JSON data
    std::string buffer;
    // Reserve the initial buffer size
    buffer.resize(SIZE_B);
    size_t bytes_written = cxl_global.fetch_setup_info(buffer,SIZE_B);
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
    int result = cxl_global.g_create_mbox(&pinfo);
    if (result>0)
    {
        cerr << "creation of memory box is unsuccessful " << endl;	    
    }
    return result;
}


/** 
 * @brief register_plugin - function mapping 
 * @param function_map  
*/  
void register_plugin(unordered_map<string, std::function<std::string(std::string)>>& function_map){
    cout << "register_plugin function called" << endl;
    function_map["ListDevices"] = ListDevices;
    function_map["ListHosts"] = ListHosts;
    function_map["AttachMemory"] = AttachMemory;
    function_map["DetachMemory"] = DetachMemory; 
    function_map["SetupInfo"] = SetupInfo;
    init_cxl_plugin();
}
