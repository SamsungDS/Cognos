#include "sla_hlpr_fns.h"

#include <nlohmann/json.hpp>

/* Helper functions */
static int parseJSONOutputOfDeviceList(
    std::string& json_data, std::vector<uint64_t>& device_id_vector) {
  int status = -1;
  std::string logger_str;

  try {
    logger_str = "JSON output " + json_data;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::DEBUG,
               logger_str.c_str());

    nlohmann::json device_list_json = nlohmann::json::parse(json_data);

    // Get the devices array
    for (const auto& device : device_list_json["devices"]) {
      uint64_t device_id = device["device_id"].get<uint64_t>();
      device_id_vector.push_back(device_id);
    }
  } catch (std::exception& e) {
    std::string exc_message = e.what();
    logger_str =
        "failed to parse JSON output for GetDeviceListFromCXLFeature. Error "
        "-> " +
        exc_message;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    return status;
  }
  status = 0;
  return status;
}

static int parseJSONOutputOfDeviceInfo(std::string node_name,
                                       std::string& json_data,
                                       DeviceInfo& dev_info) {
  int status = -1;
  nlohmann::json response_json;
  std::string logger_str;

  try {
    logger_str = "JSON output " + json_data;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::DEBUG,
               logger_str.c_str());

    response_json = nlohmann::json::parse(json_data);

    dev_info.node_name = node_name;
    dev_info.device_id = response_json["device_id"];
    dev_info.device_serial = response_json["serial_number"];
    dev_info.device_type = response_json["vendor_device_type"];
    dev_info.cxl_device_type = response_json["cxl_device_type"];
    dev_info.cxl_protocol = response_json["protocol"];
    dev_info.total_capacity_mb = response_json["total_capacity_MB"];
    dev_info.available_capacity_mb = response_json["available_capacity_MB"];
    // TODO: Need to fix on the correct way of reporting the numa_attached vs
    // the actual numa of the device
    dev_info.numa_attached = response_json["numa_node"];
    dev_info.numa = dev_info.numa_attached;
    dev_info.status = response_json["status"];

    // QOS fields
    nlohmann::json qos_json = response_json["advertised_qos"];

    dev_info.device_qos.avg_latency_ns =
        static_cast<uint64_t>(qos_json["avg_latency_ns"]);
    dev_info.device_qos.p99_latency =
        static_cast<uint64_t>(qos_json["p99_latency_ns"]);
    dev_info.device_qos.io_per_sec =
        static_cast<uint64_t>(qos_json["io_per_sec"]);
    dev_info.device_qos.bw_per_sec =
        static_cast<uint64_t>(qos_json["BW_per_sec"]);
    dev_info.device_qos.io_size =
        static_cast<uint64_t>(qos_json["io_size_in_bytes"]);
    dev_info.device_qos.queue_depth = static_cast<uint64_t>(qos_json["qd"]);
    dev_info.free_flag = true;
  } catch (std::exception& e) {
    std::string exc_message = e.what();
    logger_str =
        "failed to parse JSON output of GetDeviceInfoFromCXLFeature. Error "
        "-> " +
        exc_message;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    return status;
  }
  status = 0;
  return status;
}

static int GetDeviceListFromCXLFeature(
    std::string node_name, std::string port,
    std::vector<uint64_t>& device_id_vector) {
  std::string logger_str;
  std::string output;
  int status = -1;

  logger_str = "GetDeviceListFromCXLFeature called with node id " + node_name +
               " port " + port;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  svk::CommandRequest req_node;
  svk::CommandResponse resp_node;
  Status cmd_status;

  req_node.set_node_id(node_name);
  req_node.set_feature_name(SVK_CXL_FEATURE_NAME);
  req_node.set_command_name("list_devices");

  nlohmann::json command_param;
  command_param["device_id"] = nlohmann::json::array();
  req_node.set_command_params(command_param.dump());

  auto client = CreateClient(node_name, port);
  cmd_status = client->ProcessNodeCommand(&req_node, &resp_node);
  if (cmd_status.ok() != true) {
    logger_str = "Got error for the command device_list " + node_name +
                 " with error:" + cmd_status.error_message();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return status;
  }

  output = resp_node.node_responses(0).output();

  status = parseJSONOutputOfDeviceList(output, device_id_vector);

  if (status != 0) {
    logger_str =
        "Unable to parse the output for the DeviceList [" + output + "]";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
  }

  return status;
}

static int GetDeviceInfoFromCXLFeature(std::string node_name, std::string port,
                                       uint64_t device_id,
                                       DeviceInfo& dev_data) {
  std::string logger_str;
  std::string output;
  int status = -1;

  logger_str = "GetDeviceInfoFromCXLFeature called for device_id:" +
               std::to_string(device_id);
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  svk::CommandRequest req_node;
  svk::CommandResponse resp_node;
  Status cmd_status;

  nlohmann::json pt;
  pt["domain_id"] = "";
  pt["device_id"] = device_id;

  req_node.set_node_id(node_name);
  req_node.set_feature_name(SVK_CXL_FEATURE_NAME);
  req_node.set_command_name("get_device_info");
  req_node.set_command_params(pt.dump());

  Client client(node_name, port);
  cmd_status = client.ProcessNodeCommand(&req_node, &resp_node);
  if (cmd_status.ok() != true) {
    logger_str = "Got error for the command device_info " + node_name +
                 " with error:" + cmd_status.error_message();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return status;
  }

  output = resp_node.node_responses(0).output();

  status = parseJSONOutputOfDeviceInfo(node_name, output, dev_data);

  if (status != 0) {
    logger_str = "Unable to parse the output for the DeviceInfo " + output;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return status;
  }

  if (dev_data.device_id != device_id) {
    logger_str =
        "Received DeviceInfo for the wrong device " + dev_data.device_id;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    status = -1;
  }

  return status;
}

static bool CheckIfCXLDeviceExistInNode(std::string node_name,
                                        std::string port) {
  std::string logger_str;
  std::string output;
  bool status = false;
  nlohmann::json response_json;

  logger_str = "CheckIfCXLDeviceExistInNode  called for node" + node_name;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  svk::CommandRequest req_node;
  svk::CommandResponse resp_node;
  Status cmd_status;

  req_node.set_node_id(node_name);
  req_node.set_feature_name(SVK_NODE_FEATURE_NAME);
  req_node.set_command_name("get_node_info");
  req_node.set_command_params("{\"info_type\":\"pci\"}");
  auto client = CreateClient(node_name, port);
  // Client client(node_name, port);
  cmd_status = client->ProcessNodeCommand(&req_node, &resp_node);
  if (cmd_status.ok() != true) {
    logger_str = "Got error for the command get_node_info " + node_name +
                 " with error:" + cmd_status.error_message();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return status;
  }

  output = resp_node.node_responses(0).output();

  logger_str = "JSON output " + output;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::DEBUG, logger_str.c_str());

  try {
    response_json = nlohmann::json::parse(output);
    if (response_json.contains("pci-info")) {
      for (const auto& pci : response_json["pci-info"]) {
        std::string device_type = pci.at("device_type");
        if (device_type == "cxl") {
          status = true;
          logger_str = "Found a PCI device type with CXL";
          svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                     logger_str.c_str());
          break;
        }
      }
    } else {
      logger_str = "pci-info not found in JSON output";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                 logger_str.c_str());
      status = false;
    }
  } catch (nlohmann::json::exception& e) {
    std::string exc_message = e.what();
    logger_str =
        "failed to parse JSON output of GetNodeInfo. Error -> " + exc_message;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    status = false;
  }

  return status;
}

int SLADeviceHelper::GetDeviceDetails(std::string node_name, std::string port) {
  std::string logger_str;
  std::string output;
  int status = -1;
  std::vector<uint64_t> device_id_vector;

  logger_str =
      "running GetDeviceDetails with node id " + node_name + " port " + port;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  // Check for CXL tag in the PCI device info from the node. If present,
  // read the actual CXL devices. Otherwise, skip and return success
  if (CheckIfCXLDeviceExistInNode(node_name, port) == false) {
    logger_str = "Error in getting node info for the node " + node_name +
                 " or the CXL device is not present";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    status = 0;
    return status;
  }

  status = GetDeviceListFromCXLFeature(node_name, port, device_id_vector);
  if (status != 0) {
    logger_str = "Unable to get the GetDeviceListFromCXLFeature for the node " +
                 node_name;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return status;
  }

  for (uint64_t device_id : device_id_vector) {
    DeviceInfo dev_info;

    status = GetDeviceInfoFromCXLFeature(node_name, port, device_id, dev_info);
    if (status != 0) {
      logger_str = "Failed to get device info for " + std::to_string(device_id);
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                 logger_str.c_str());
      return status;
    }
    bool duplicate_device = false;
    for (size_t i = 0; i < this->m_device_info.size(); i++) {
      DeviceInfo d = this->m_device_info[i];
      if (dev_info.device_id == d.device_id && node_name == d.node_name) {
        this->m_device_info[i] = dev_info;
        logger_str = "Device id <" + std::to_string(device_id) +
                     "> has already been added to controller for tracking, "
                     "replacing the device info.";
        duplicate_device = true;
        break;
      }
    }
    if (!duplicate_device) {
      logger_str = "Device id <" + std::to_string(device_id) +
                   "> added to controller for tracking.";
      this->m_device_info.push_back(dev_info);
    }
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
  }

  logger_str = "Successfully populated the devices for the node " + node_name;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  status = 0;
  return status;
}

int SLADeviceHelper::GetDeviceForAppRequirements(
    uint64_t sla_latency_ns, uint64_t size, std::vector<DeviceInfo>& devices) {
  int status = 0;
  std::string logger_str;

  // Sort the devices with high avg_latency_ns at the top
  std::vector<DeviceInfo> sorted_devices = this->m_device_info;
  std::sort(sorted_devices.begin(), sorted_devices.end(),
            [](const DeviceInfo& a, const DeviceInfo& b) {
              return a.device_qos.avg_latency_ns > b.device_qos.avg_latency_ns;
            });

  for (DeviceInfo dev : sorted_devices) {
    logger_str = "device " + std::to_string(dev.device_id) + " has latency " +
                 std::to_string(dev.device_qos.avg_latency_ns);
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    if (dev.free_flag && sla_latency_ns >= dev.device_qos.avg_latency_ns) {
      logger_str = "device " + std::to_string(dev.device_id) + " with numa " +
                   std::to_string(dev.numa) +
                   " added to the list for consumption";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
      // dev.free_flag = false;
      devices.push_back(dev);
    }
  }

  if (devices.size() == 0) {
    status = -1;
  }
  return status;
}

int SLADeviceHelper::UnregisterDevicesForNode(std::string node_name) {
  int status = -1;
  std::string logger_str;
  for (DeviceInfo dev : this->m_device_info) {
    if (dev.free_flag != true) {
      // Should we return error as the device is associated with an app
      // Ignoring for now
      logger_str = "device " + std::to_string(dev.device_id) + " with numa " +
                   std::to_string(dev.numa) + " is in use";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
      return status;
    }
  }

  this->m_device_info.erase(
      std::remove_if(
          this->m_device_info.begin(), this->m_device_info.end(),
          [node_name](DeviceInfo d) { return d.node_name == node_name; }),
      this->m_device_info.end());

  status = 0;

  return status;
}

int SLADeviceHelper::GetDeviceInfo(std::string device_id,
                                   DeviceInfo& device_info) {
  std::vector<DeviceInfo> devices = this->m_device_info;
  for (DeviceInfo dev : devices) {
    if (dev.device_id == std::stoull(device_id)) {
      device_info = dev;
      return 0;
    }
  }
  return -1;
}

int SLADeviceHelper::GetAppInfo(std::string device_id, App_Info& app_info) {
  auto it = this->m_device_app_data.find(device_id);
  if (it != this->m_device_app_data.end()) {
    app_info = it->second;
    return 0;
  }
  return -1;
}

int SLADeviceHelper::SetSLADataForApp(std::string device_id,
                                      App_Info app_info) {
  this->m_device_app_data[device_id] = app_info;
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