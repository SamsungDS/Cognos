

#include "node_cmd_helper_fns.h"

// The "output" param is valid only if the command is successful. Check the
// value of return data structure "Status". if Status.ok() is true, the
// command is successful. Else it is failure and can check the error message
// using Status.error_message()
Status SendNodeCommand(const std::string& node_name,
                       const std::string& node_port,
                       const std::string& feature_name,
                       const std::string& command_name,
                       const std::string& command_params, std::string& output) {
  svk::CommandRequest req_node;
  svk::CommandResponse resp_node;
  Status cmd_status;
  std::string logger_str;

  req_node.set_node_id(node_name);
  req_node.set_feature_name(feature_name);
  req_node.set_command_name(command_name);
  req_node.set_command_params(command_params);

  logger_str =
      "Sending command to node with the following - node_name: " + node_name +
      " node_port: " + node_port + " feature_name: " + feature_name +
      " command_name: " + command_name + " command_params: " + command_params;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  auto client = CreateClient(node_name, node_port);
  cmd_status = client->ProcessNodeCommand(&req_node, &resp_node);
  if (cmd_status.ok() != true) {
    logger_str = "Got error for the command " + command_name + " on node " +
                 node_name + " with error:" + cmd_status.error_message();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
  } else {
    logger_str = "Send command to the node with command_name: " + command_name +
                 " and command_params: " + command_params + " is successful";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());

    if (resp_node.node_responses_size() > 0) {
      output = resp_node.node_responses(0).output();
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, output.c_str());
    }
  }

  return cmd_status;
}
