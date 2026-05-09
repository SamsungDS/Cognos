

#include "node_cmd_helper_fns.h"

#include "grpc_controller.h"

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
      logger_str = "Output of the command is " + output;
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
    }
  }

  return cmd_status;
}

// Enable RAS Tracking on the devices added for SLAT as well
// Ignoring the errors of node command until the RAS feature is completed
int EnableRASTrackingOnDevices(
    const std::string& node_name, const std::string& node_port,
    const std::unordered_map<std::string, DeviceInfo>& ras_device_map) {
  int status = -1;
  std::string log_msg;
  std::string output;

  // Send each device to RAS feature module for reliability tracking
  for (const auto& [device_id, device_info] : ras_device_map) {
    json command_params_json;
    json configure_options_json;
    command_params_json["device_id"] = device_info.controller_generated_id;
    command_params_json["device_numa"] = device_info.numa;
    command_params_json["device_type"] = device_info.device_type;
    configure_options_json["error_count_threshold"] = ERROR_COUNT_THRESHOLD;
    command_params_json["configure_options"] = configure_options_json;

    log_msg = "Enable RAS tracking with params " + command_params_json.dump();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, log_msg.c_str());

    SendNodeCommand(node_name, node_port, RAS_FEATURE_MODULE_NAME,
                    "add_reliability_monitoring_for_device",
                    command_params_json.dump(), output);
  }

  status = 0;
  return status;
}

/**
 * Disable the RAS tracking on this device.
 *
 * @return 0 if the device is disabled, -1 on failure.
 */

int DisableRASTrackingOnDevice(const std::string& node_name,
                               const std::string& node_port,
                               const std::string& device_id,
                               const std::string& device_type,
                               const std::string& device_numa) {
  Status cmd_status;
  int status = -1;
  std::string log_msg;
  std::string output;

  log_msg = "Initiated Disable RAS tracking on device " + device_id;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, log_msg.c_str());

  // Send each device to RAS feature module for reliability tracking
  json command_params_json;
  command_params_json["device_id"] = device_id;
  command_params_json["device_numa"] = device_numa;
  command_params_json["device_type"] = device_type;

  log_msg = "Disabling RAS tracking with params " + command_params_json.dump();
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, log_msg.c_str());

  cmd_status = SendNodeCommand(node_name, node_port, RAS_FEATURE_MODULE_NAME,
                               "remove_reliability_monitoring_for_device",
                               command_params_json.dump(), output);
  if (cmd_status.ok()) {
    log_msg = "Disabled RAS tracking on device " + device_id;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, log_msg.c_str());
    status = 0;
  }

  return status;
}

int UpdateClusterName(const std::string& cluster_name,
                      const std::vector<node_info>& node_list) {
  svk::NodeConfigRequest req_node;
  svk::NodeConfigResponse resp_node;
  int status = 0;
  Status cmd_status;
  std::string logger_str;

  req_node.set_cluster_name_flag(true);
  req_node.set_cluster_name(cluster_name);

  for (const auto& n : node_list) {
    logger_str =
        "Updating the cluster name on node with the following - node_name: " +
        n.node_name + " node_port: " + n.node_port;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());

    auto client = CreateClient(n.node_ip, n.node_port);
    cmd_status = client->ProcessNodeConfiguration(&req_node, &resp_node);
    if (cmd_status.ok() != true) {
      logger_str = "Got error in updating the cluster name on node " +
                   n.node_name + " with error:" + cmd_status.error_message();
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                 logger_str.c_str());
      status = -1;
      break;
    } else {
      logger_str =
          "Update of cluster name is successful on node " + n.node_name;
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
    }
  }

  if (status == 0) {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               "Successfully updated the cluster name on all nodes");
  } else {
    // Remove the cluster name if partially done on those nodes

    req_node.set_cluster_name("");

    for (const auto& n : node_list) {
      logger_str =
          "Rollbacking the changes of cluster name on node with the following "
          "- node_name: " +
          n.node_name + " node_port: " + n.node_port;
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());

      auto client = CreateClient(n.node_ip, n.node_port);
      cmd_status = client->ProcessNodeConfiguration(&req_node, &resp_node);
      if (cmd_status.ok() != true) {
        logger_str = "Got error in rollback of the cluster name on node " +
                     n.node_name + " with error:" + cmd_status.error_message();
        svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                   logger_str.c_str());
      } else {
        logger_str =
            "Rollback of the cluster name is successful on node " + n.node_name;
        svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                   logger_str.c_str());
      }
    }
  }

  return status;
}