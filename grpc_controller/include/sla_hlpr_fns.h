#ifndef __SLA_HLPR_FNS_H__
#define __SLA_HLPR_FNS_H__

#include <algorithm>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <unordered_map>
#include <vector>

#include "client_library.h"
#include "framework/framework.grpc.pb.h"
#include "framework_struct.h"
#include "grpc_controller.h"
#include "grpc_hdr.h"
#include "svk_logger.h"
#include "svk_pub_sub_struct.h"
#include "svk_publisher.h"

#define SLA_CONFIG_DIR "/usr/local/svk/mgmt-fw/config/"
#define SLA_CONFIG_FILE SLA_CONFIG_DIR "/device_sla_config.json"

typedef struct {
  uint64_t avg_latency_ns;  // Device Latency in nanoseconds
  uint64_t p99_latency;
  uint64_t io_per_sec;
  uint64_t bw_per_sec;
  uint64_t io_size;
  uint64_t queue_depth;
} DeviceQOS;

typedef struct DeviceInfo_T {
  std::string node_name;
  std::string device_name;
  std::string device_type;
  uint64_t total_capacity;
  uint64_t available_capacity;
  std::string status; /* attach/remote/direct */
  uint64_t numa;
  DeviceQOS device_qos;
  svk_slat_logic_output stats;
  bool free_flag;
} DeviceInfo;

typedef struct {
  uint64_t appLatencyns;
  uint64_t size;
  std::vector<DeviceInfo> device_info;  // Array of pointers pointing to the
                                        // devices in the device_info array
} App_Device_List;

class SLADeviceHelper {
 public:
  SLADeviceHelper(std::string config_file);
  int GetDeviceInfo(std::string node_name, std::string port);
  int GetDeviceForAppRequirements(uint64_t sla_latency_ns, uint64_t size,
                                  std::vector<DeviceInfo>& devices);
  int SetSLADataForApp(std::string app_name, App_Device_List sla_data);
  int UnregisterDevicesForNode(std::string node_name);
  std::vector<DeviceInfo> GetDevices() { return this->device_info; };
  void SetDevices(std::vector<DeviceInfo>& devices) {
    this->device_info = devices;
  };
  ~SLADeviceHelper(){};

 private:
  std::string config_file;
  std::vector<DeviceInfo> device_info;
  // unordered map with app_name and the SLA data
  std::unordered_map<std::string, App_Device_List> app_device_data;
};

class SLAStatsManager {
 public:
  SLAStatsManager(){};
  ~SLAStatsManager(){};
  bool addSLADataEntry(const std::string& app_name,
                       const std::string& host_name,
                       const std::string& device_name,
                       svk_slat_logic_output data);
  // Get data based on specific tuple
  svk_slat_logic_output getSLAData(const std::string& app_name,
                                   const std::string& host_name,
                                   const std::string& device_name);
  bool updateSLAData(const std::string& app_name, const std::string& host_name,
                     const std::string& device_name,
                     svk_slat_logic_output data);
  // Get all entries that include name in the tuple
  std::map<std::tuple<std::string, std::string, std::string>,
           svk_slat_logic_output>
  searchSLAData(const std::string& name);
  bool writeToFile(const std::string& filename);
  bool readFromFile(const std::string& filename);

 private:
  std::map<std::tuple<std::string, std::string, std::string>,
           svk_slat_logic_output>
      stats;
};

#endif /* __SLA_HLPR_FNS_H__ */