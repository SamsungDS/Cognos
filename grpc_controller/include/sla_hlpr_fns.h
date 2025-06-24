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
  uint64_t device_id;
  uint64_t device_serial;
  std::string device_type;
  std::string cxl_device_type;
  std::string cxl_protocol;
  uint64_t total_capacity_mb;
  uint64_t available_capacity_mb;
  std::string status;
  uint64_t numa;
  uint64_t numa_attached;
  DeviceQOS device_qos;
  svk_slat_logic_output stats;
  bool free_flag;
} DeviceInfo;

typedef struct {
  std::string app_name;
  uint64_t appLatencyns;
  uint64_t size;
} App_Info;

class SLADeviceHelper {
 public:
  SLADeviceHelper(){};
  int GetDeviceDetails(std::string node_name, std::string port);
  int GetDeviceForAppRequirements(uint64_t sla_latency_ns, uint64_t size,
                                  std::vector<DeviceInfo>& devices);
  int SetSLADataForApp(std::string device_id, App_Info app_info);
  int UnregisterDevicesForNode(std::string node_name);
  int GetDeviceInfo(std::string device_id, DeviceInfo& device_info);
  int GetAppInfo(std::string device_id, App_Info& app_info);
  ~SLADeviceHelper(){};

 private:
  std::vector<DeviceInfo> m_device_info;
  // unordered map with device_id with the App details
  std::unordered_map<std::string, App_Info> m_device_app_data;
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