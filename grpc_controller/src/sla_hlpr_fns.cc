#include "sla_hlpr_fns.h"

/* Helper functions */
int parseJSONOutput(std::string json_data, std::vector<DeviceInfo>& dev_data) {
  int status = -1;
  std::string device_type;
  boost::property_tree::ptree setup_info_pt;
  boost::property_tree::ptree device_sla_pt;
  std::string logger_str;

  try {
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
        dev_info.node_name = device_ptree.second.get<std::string>("node_name");
        dev_info.numa = device_ptree.second.get<uint64_t>("dev_numa");
        dev_info.device_qos.avg_latency_ns =
            device_ptree.second.get<uint64_t>("sla_avg_latency_ns");
        dev_info.free_flag = true;

        dev_data.push_back(dev_info);
      }
    }
  } catch (std::exception& e) {
    std::string exc_message = e.what();
    logger_str = "failed to process command setupinfo. Error -> " + exc_message;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    return status;
  }

  status = 0;
  return status;
}

SLADeviceHelper::SLADeviceHelper(std::string config_file) {
  this->config_file = config_file;
}

int SLADeviceHelper::GetDeviceInfo(std::string node_name, std::string port) {
  std::string logger_str;
  std::string output;
  int status = -1;
  int parser_status = -1;
  std::vector<DeviceInfo> dev_data;

  logger_str = "running setupinfo with node id " + node_name + " port " + port;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

#if 0
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
#endif
  struct stat fstat;

  if (stat(this->config_file.c_str(), &fstat) != 0) {
    // TODO: Needs to remove this once the SetupInfo is properly supported.
    // File not present. Return success
    logger_str = "SLA Config file at " + this->config_file +
                 " not found for the command SetupInfo. Returning as success";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return 0;
  }

  std::ifstream fh(this->config_file);
  std::string file_data((std::istreambuf_iterator<char>(fh)),
                        (std::istreambuf_iterator<char>()));
  fh.close();
  output = file_data;

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

  logger_str = "Successfully parsed the output and populated the devices";
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  status = 0;
  return status;
}

int SLADeviceHelper::GetDeviceForAppRequirements(
    uint64_t sla_latency_ns, uint64_t size, std::vector<DeviceInfo>& devices) {
  int status = 0;
  std::string logger_str;
  for (DeviceInfo dev : this->device_info) {
    if (dev.free_flag && sla_latency_ns >= dev.device_qos.avg_latency_ns) {
      logger_str = "device " + dev.device_name + " with numa " +
                   std::to_string(dev.numa) +
                   " added to the list for consumption";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
      dev.free_flag = false;
      devices.push_back(dev);
    }
  }

  if (devices.size() == 0) {
    status = -1;
  }
  return status;
}

int SLADeviceHelper::SetSLADataForApp(std::string app_name,
                                      App_Device_List app_device_data) {
  this->app_device_data[app_name] = app_device_data;
  return 0;
}

bool SLAStatsManager::addSLADataEntry(const std::string& app_name,
                                      const std::string& host_name,
                                      const std::string& device_name,
                                      svk_slat_logic_output data) {
  std::string logger_str;
  auto key = std::make_tuple(app_name, host_name, device_name);
  if (stats.find(key) != stats.end()) {
    logger_str =
        "SLA stats with given app_name/host_name/device_name exists already. "
        "Will attempt to update entry.";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    return this->updateSLAData(app_name, host_name, device_name, data);
  }
  stats[key] = data;
  return true;
}

svk_slat_logic_output SLAStatsManager::getSLAData(
    const std::string& app_name, const std::string& host_name,
    const std::string& device_name) {
  auto key = std::make_tuple(app_name, host_name, device_name);
  auto it = stats.find(key);
  if (it != stats.end()) {
    return it->second;
  } else {
    throw std::runtime_error("SLA data not found for given tuple.");
  }
}

bool SLAStatsManager::updateSLAData(const std::string& app_name,
                                    const std::string& host_name,
                                    const std::string& device_name,
                                    svk_slat_logic_output data) {
  std::string logger_str;
  auto key = std::make_tuple(app_name, host_name, device_name);
  if (stats.find(key) == stats.end()) {
    logger_str = "Unable to find entry for " + app_name + ", " + host_name +
                 ", " + device_name + ". Could not update SLA stats.";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return false;
  }
  stats[key] = data;
  return true;
}

std::map<std::tuple<std::string, std::string, std::string>,
         svk_slat_logic_output>
SLAStatsManager::searchSLAData(const std::string& name) {
  std::map<std::tuple<std::string, std::string, std::string>,
           svk_slat_logic_output>
      results;
  for (const auto& [key, value] : stats) {
    const auto& [k1, k2, k3] = key;
    if (k1 == name || k2 == name || k3 == name) {
      results[key] = value;
    }
  }
  if (results.size() == 0) {
    std::string logger_str = "No SLA data found for the given name.";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
  }
  return results;
}

bool SLAStatsManager::writeToFile(const std::string& filename) {
  std::ofstream outfile(filename);
  std::string logger_str =
      "SLA stats file was unabled to be opened for writing.";
  if (!outfile.is_open()) {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return false;
  }
  for (const auto& [key, val] : stats) {
    // Write SLA data as bytes
    outfile.write((char*)&val, sizeof(svk_slat_logic_output));
    if (!outfile) {
      logger_str = "Error while writing SLA stats to file.";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                 logger_str.c_str());
      return false;
    }
  }

  return true;
}

bool SLAStatsManager::readFromFile(const std::string& filename) {
  std::ifstream infile(filename, std::ios::binary);
  if (!infile.is_open()) {
    std::string logger_str =
        "SLA stats file was unabled to be opened for reading.";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return false;
  }
  std::map<std::tuple<std::string, std::string, std::string>,
           svk_slat_logic_output>
      new_stats;
  while (infile.peek() != EOF) {
    try {
      // Read SLA data as bytes
      svk_slat_logic_output data;
      infile.read((char*)&data, sizeof(svk_slat_logic_output));

      std::string app_name(data.app_name);
      std::string host_name(data.host_name);
      std::string device_name(data.device_name);

      new_stats[std::make_tuple(app_name, host_name, device_name)] = data;
    } catch (std::exception& e) {
      std::string exc = e.what();
      std::string logger_str = "Error while reading SLA stats file: " + exc;
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                 logger_str.c_str());
      return false;
    }
  }
  stats = new_stats;
  return true;
}
