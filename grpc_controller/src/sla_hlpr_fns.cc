#include "sla_hlpr_fns.h"

/* Helper functions */
int parseJSONOutput(std::string json_data, std::vector<DeviceInfo>& dev_data) {
  int status = 0;
  std::string device_type;
  boost::property_tree::ptree setup_info_pt;
  boost::property_tree::ptree device_sla_pt;

  std::istringstream iss(json_data);
  boost::property_tree::read_json(iss, setup_info_pt);

  for (const auto& element : setup_info_pt) {
    // Each element is a ptree itself
    device_type = element.second.get<std::string>("type");
    for (const auto& device_ptree : element.second.get_child("Devices")) {
      DeviceInfo dev_info;
      dev_info.device_type = device_type;
      dev_info.device_name = device_ptree.second.get<std::string>("dev_name");
      dev_info.total_capacity = device_ptree.second.get<uint64_t>("dev_size");
      dev_info.device_qos.avg_latency_us =
          device_ptree.second.get<uint64_t>("sla_avg_latency_us");

      dev_data.push_back(dev_info);
    }
  }
  return status;
}

int SLADeviceHelper::GetDeviceInfo(std::string node_name, std::string port) {
  std::string logger_str;
  std::string output;
  int status = -1;
  int parser_status;
  std::vector<DeviceInfo> dev_data;

  logger_str = "running setupinfo with node id " + node_name + " port " + port;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  try {
#ifdef CXL_SLA_ENABLED
    svk::CommandRequest req_node;
    svk::CommandResponse resp_node;
    Status cmd_status;

    req_node.set_node_id(node_name);
    req_node.set_feature_id(feature_id::CXL);
    req_node.set_feature_params("command=SetupInfo");

    Client client(node_name, port);
    cmd_status = client.ProcessNodeCommand(&req_node, &resp_node);
    if (cmd_status.ok() != true) {
      logger_str = "Got error for the command SetupInfo " + node_name;
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                 logger_str.c_str());
      return status;
    }

    output = resp_node.node_responses(0).output();
#else
    std::ifstream fh(SLA_CONFIG_FILE);
    std::string file_data((std::istreambuf_iterator<char>(fh)),
                          (std::istreambuf_iterator<char>()));
    fh.close();
    output = file_data;
#endif
    parser_status = parseJSONOutput(output, dev_data);

    if (parser_status != 0) {
      logger_str = "Unable to parse the output for the SetupInfo " + output;
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                 logger_str.c_str());
      return status;
    }

    for (DeviceInfo dev : dev_data) {
      // Need to add a mechanism to generate unique id for each dev entry as
      // hashing for future modifications
      this->device_info.push_back(dev);
    }
  } catch (std::exception& e) {
    std::string exc_message = e.what();
    logger_str = "failed to process command setupinfo. Error -> " + exc_message;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    return status;
  }
  logger_str = "Successfully parsed the output and populated the devices";
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  status = 0;
  return status;
}