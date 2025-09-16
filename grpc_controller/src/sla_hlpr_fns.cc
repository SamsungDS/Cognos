#include "sla_hlpr_fns.h"

#include <nlohmann/json.hpp>

/* Helper functions */

// The "output" param is valid only if the command is successful. Check the
// value of return data structure "Status". if Status.ok() is true, the
// command is successful. Else it is failure and can check the error message
// using Status.error_message()
Status SendNodeCommand(std::string node_name, std::string node_port,
                       std::string feature_name, std::string command_name,
                       std::string command_params, std::string& output) {
  svk::CommandRequest req_node;
  svk::CommandResponse resp_node;
  Status cmd_status;
  std::string logger_str;

  req_node.set_node_id(node_name);
  req_node.set_feature_name(feature_name);
  req_node.set_command_name(command_name);
  req_node.set_command_params(command_params);

  auto client = CreateClient(node_name, node_port);
  cmd_status = client->ProcessNodeCommand(&req_node, &resp_node);
  if (cmd_status.ok() != true) {
    logger_str = "Got error for the command " + command_name + " on node " +
                 node_name + " with error:" + cmd_status.error_message();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
  } else {
    output = resp_node.node_responses(0).output();
  }

  return cmd_status;
}

/*
 The JSON output of CXL feature module's list_devices is as follows
 {
  "devices": [
    {
      "device_id": 29690035288064,
      "vendor_device_type": "CMM-D",
      "pcie_addr": "0000:b8:00.0"
    },
    {
      "device_id": 29690035260416,
      "vendor_device_type": "CMM-D",
      "pcie_addr": "0000:4c:00.0"
    }
  ]
}
*/
static int parseJSONOutputOfDeviceList(
    std::string& json_data, std::vector<uint64_t>& device_id_vector) {
  int status = -1;
  std::string logger_str;

  try {
    logger_str = "JSON output of CXL device list " + json_data;
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
        "failed to parse JSON output for GetDeviceListFromCXLFeature. "
        "Output: " +
        json_data + ", Error -> " + exc_message;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return status;
  }
  status = 0;
  return status;
}

/*
 The JSON output of the device info from CXL feature module or the node feature
module is very similar except the cxl protocol and the transport type

 Output from node feature module is
 {
  "device-info": {
    "24598aa6-edf7-3cce-a962-5e60d75d546a": {
      "advertised_qos": {
        "BW_per_sec": 35000000000,
        "avg_latency_ns": 100,
        "io_per_sec": 8000000,
        "io_size_in_bytes": 4096,
        "p99_latency_ns": 100,
        "qd": 32
      },
      "available_capacity_MB": 124375,
      "device_id": 0,
      "numa_node": 0,
      "serial_number": "24598aa6-edf7-3cce-a962-5e60d75d546a",
      "status": "online",
      "total_capacity_MB": 128557,
      "vendor_device_type": "DRAM"
    }
  }

  Output from CXL feature module is

{
  "api_version": 1,
  "device_id": 29690035288064,
  "manufacturer": "samsung",
  "serial_number": 305419897,
  "FW_revision": "1.0.0",
  "location": "0000:b8:00.0",
  "total_capacity_MB": 258047,
  "feature_supported": "basic",
  "vendor_device_type": "CMM-D",
  "cxl_device_type": "Type3",
  "protocol": "CXL 2.0",
  "port_type": "root",
  "mode_discovered": "auto",
  "connection_type": "CXL.mem",
  "domain_type": "PCIe",
  "domain_id": 0,
  "link_speed_GT_s": 32,
  "link_width": 8,
  "available_capacity_MB": 257927,
  "status": "Healthy",
  "aspm_active": false,
  "sris_active": false,
  "lock_active": false,
  "numa_node": 2,
  "capabilities": {
    "Power Management version": 1
  },
  "advertised_qos": {
    "avg_latency_ns": 120,
    "p99_latency_ns": 350,
    "io_per_sec": 50000,
    "BW_per_sec": 1000000,
    "io_size_in_bytes": 4096,
    "qd": 32
  }
}

*/
static int parseJSONOutputOfDeviceInfo(std::string node_name,
                                       std::string& json_data,
                                       DeviceInfo& dev_info) {
  int status = -1;
  nlohmann::json response_json;
  std::string logger_str;

  try {
    logger_str = "JSON output of Device Info " + json_data;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::DEBUG,
               logger_str.c_str());

    response_json = nlohmann::json::parse(json_data);

    dev_info.node_name = node_name;
    dev_info.device_id = response_json["device_id"];

    // Since there is no proper serial number for the CXL devices, this can
    // be expected in either integer or a string. Convert to string
    // irrespective of the type.
    if (response_json["serial_number"].is_number()) {
      uint64_t serial = response_json["serial_number"];
      dev_info.device_serial = std::to_string(serial);
    } else {
      dev_info.device_serial = response_json["serial_number"];
    }
    dev_info.device_type = response_json["vendor_device_type"];
    dev_info.cxl_device_type = response_json.value("cxl_device_type", "");
    dev_info.cxl_protocol = response_json.value("protocol", "");
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
        "failed to parse JSON output of GetDeviceInfoFromCXLFeature. Output: " +
        json_data + ", Error -> " + exc_message;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return status;
  }
  status = 0;
  return status;
}

/*
 This function gets the list of devices detected by the CXL feature modules.
 It contains the device IDs which are used for subsequent calls to
 GetDeviceInfoFromCXLFeature.
*/
static int GetDeviceListFromCXLFeature(
    std::string node_name, std::string port,
    std::vector<uint64_t>& device_id_vector) {
  std::string logger_str;
  std::string output;
  int status = -1;

  logger_str = "GetDeviceListFromCXLFeature called with node id " + node_name +
               " port " + port;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  Status cmd_status;
  nlohmann::json command_param;
  command_param["device_id"] = nlohmann::json::array();

  cmd_status = SendNodeCommand(node_name, port, SVK_CXL_FEATURE_NAME,
                               "list_devices", command_param.dump(), output);
  if (cmd_status.ok() != true) {
    logger_str = "Got error for the command device_list " + node_name +
                 " with error:" + cmd_status.error_message();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return status;
  }

  status = parseJSONOutputOfDeviceList(output, device_id_vector);

  if (status != 0) {
    logger_str =
        "Unable to parse the output for the DeviceList [" + output + "]";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
  }

  return status;
}

/*
 The function is to get the CXL device info for the given device ID
*/
static int GetDeviceInfoFromCXLFeature(std::string node_name, std::string port,
                                       uint64_t device_id,
                                       DeviceInfo& dev_info) {
  std::string logger_str;
  std::string output;
  int status = -1;

  logger_str = "GetDeviceInfoFromCXLFeature called for device_id:" +
               std::to_string(device_id);
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  Status cmd_status;

  nlohmann::json command_param;
  command_param["domain_id"] = "";
  command_param["device_id"] = device_id;

  cmd_status = SendNodeCommand(node_name, port, SVK_CXL_FEATURE_NAME,
                               "get_device_info", command_param.dump(), output);
  if (cmd_status.ok() != true) {
    logger_str = "Got error for the command device_info " + node_name +
                 " with error:" + cmd_status.error_message();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return status;
  }

  status = parseJSONOutputOfDeviceInfo(node_name, output, dev_info);

  if (status != 0) {
    logger_str = "Unable to parse the output for the DeviceInfo " + output;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return status;
  }

  if (dev_info.device_id != device_id) {
    logger_str =
        "Received DeviceInfo for the wrong device " + dev_info.device_id;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    status = -1;
  }

  if (status == 0) {
    // Update the ID to be unique as the serial number/device_id is not unique
    // across nodes
    dev_info.controller_generated_id =
        dev_info.node_name + "-" + std::to_string(dev_info.numa_attached);
  }

  return status;
}

// Check if the CXL devices are present or not based on the node feature
// module's pci information
static bool CheckIfCXLDeviceExistInNode(std::string node_name,
                                        std::string port) {
  std::string logger_str;
  std::string output;
  bool status = false;
  nlohmann::json response_json;

  logger_str = "CheckIfCXLDeviceExistInNode  called for node" + node_name;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  Status cmd_status;
  std::string command_params = "{\"info_type\":\"pci\"}";

  cmd_status = SendNodeCommand(node_name, port, SVK_NODE_FEATURE_NAME,
                               "get_node_info", command_params, output);
  if (cmd_status.ok() != true) {
    logger_str = "Got error for the command get_node_info " + node_name +
                 " with error:" + cmd_status.error_message();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return status;
  }

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

/*
  Get the list of CXL device IDs from the CXL feature module
*/
int GetCXLDeviceDetails(std::string node_name, std::string port,
                        std::vector<DeviceInfo>& device_map) {
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
    logger_str = "CXL feature not loaded or error from the node " + node_name +
                 ". Ignoring";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    status = 0;
    return status;
  }

  for (uint64_t device_id : device_id_vector) {
    DeviceInfo dev_info;

    // Get the CXL device info from the CXL feature module. In case of failure,
    // return an error
    status = GetDeviceInfoFromCXLFeature(node_name, port, device_id, dev_info);
    if (status != 0) {
      logger_str = "Failed to get device info for " + std::to_string(device_id);
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                 logger_str.c_str());
      return status;
    }
    device_map.push_back(dev_info);
  }

  logger_str = "Successfully populated the devices for the node " + node_name;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  status = 0;
  return status;
}

/*
  Function to get only the DRAM devices from the node feature module.
*/
int GetDRAMDeviceDetails(std::string node_name, std::string port,
                         std::vector<DeviceInfo>& device_map) {
  std::string logger_str;
  std::string output;
  int status = -1;

  logger_str = "running GetDRAMDeviceDetails with node id " + node_name +
               " port " + port;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  nlohmann::json response_json;
  Status cmd_status;
  std::string command_params = "{\"info_type\":\"device\"}";

  cmd_status = SendNodeCommand(node_name, port, SVK_NODE_FEATURE_NAME,
                               "get_node_info", command_params, output);
  if (cmd_status.ok() != true) {
    logger_str = "Got error for the command get_node_info for device from" +
                 node_name + " with error:" + cmd_status.error_message() +
                 ".\n";
    logger_str +=
        "Can be because of node module not loaded or failed. Ignoring the "
        "error";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    // If the node feature module is not loaded, this can fail. Returning
    // success in case of failure
    status = 0;
    return status;
  }

  logger_str = "Node feature module's get device info returned " + output;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::DEBUG, logger_str.c_str());

  try {
    response_json = nlohmann::json::parse(output);
    if (!response_json.contains("device-info")) {
      return status;
    }
    std::string json_data;
    for (const auto& device_id : response_json["device-info"].items()) {
      DeviceInfo dev;
      json_data = device_id.value().dump();
      status = parseJSONOutputOfDeviceInfo(node_name, json_data, dev);
      if (status != 0) {
        logger_str = "Failed to parse the data for the device " + json_data;
        svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                   logger_str.c_str());
        return status;
      }

      // Update the ID to be unique as the serial number/device_id is not unique
      // across nodes
      dev.controller_generated_id =
          dev.node_name + std::to_string(dev.numa_attached);

      device_map.push_back(dev);
    }
  } catch (nlohmann::json::exception& e) {
    std::string exc_message = e.what();
    logger_str =
        "failed to parse JSON output of get_node_info for device. Error -> " +
        exc_message;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    status = -1;
    return status;
  }

  status = 0;
  return status;
}

/*
  Get all the DRAM and CXL devices and update the controller's device array
*/
int SLADeviceHelper::GetDeviceDetails(std::string node_name, std::string port) {
  int status = -1;
  std::vector<DeviceInfo> device_map;
  std::string logger_str;

  GetDRAMDeviceDetails(node_name, port, device_map);
  GetCXLDeviceDetails(node_name, port, device_map);

  for (DeviceInfo dev_info : device_map) {
    bool duplicate_device = false;
    for (size_t i = 0; i < this->m_device_info.size(); i++) {
      DeviceInfo d = this->m_device_info[i];
      if (dev_info.controller_generated_id == d.controller_generated_id) {
        this->m_device_info[i] = dev_info;
        logger_str = "Device id <" + dev_info.controller_generated_id +
                     "> has already been added to controller for tracking";
        duplicate_device = true;
        break;
      }
    }
    if (!duplicate_device) {
      this->m_device_info.push_back(dev_info);
      logger_str = "Device id <" + std::to_string(dev_info.device_id) +
                   "> from node " + dev_info.node_name +
                   " is added to controller for tracking.";
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