#ifndef LOGICMOCK
#define LOGICMOCK

#include <logic_interface/svk_logic_interface.h>

#include <string>

#define CONFIG_FILE "config/mock_config.json"

using namespace std;

// Initialization function
int startup(char const *cfg);

// Generic request function using a JSON string
string processRequest(string &request);

extern "C" svk_status execute_mock_logic_sync(svk_logic_cmd *cmd,
                                              svk_logic_input *input,
                                              svk_logic_output *output);

extern "C" svk_status execute_mock_logic_async(
    svk_logic_cmd *pass_thru, svk_postprocess_fn *postprocess_fn);

extern "C" svk_status cleanup_mock_logic_module(void *param);

#endif
