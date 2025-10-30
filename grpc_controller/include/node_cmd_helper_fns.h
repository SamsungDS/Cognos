#ifndef __NODE_CMD_HELPER_FNS_H__
#define __NODE_CMD_HELPER_FNS_H__
#include "grpc_controller.h"

// The "output" param is valid only if the command is successful. Check the
// value of return data structure "Status". if Status.ok() is true, the
// command is successful. Else it is failure and can check the error message
// using Status.error_message()
Status SendNodeCommand(const std::string& node_name,
                       const std::string& node_port,
                       const std::string& feature_name,
                       const std::string& command_name,
                       const std::string& command_params, std::string& output);

#endif /*__NODE_CMD_HELPER_FNS_H__*/
