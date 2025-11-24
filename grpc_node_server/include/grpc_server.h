#ifndef __GRPC_SERVER_H__
#define __GRPC_SERVER_H__
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <nlohmann/json.hpp>
#include <unordered_map>

#include "framework/framework.grpc.pb.h"
#include "framework_struct.h"
#include "framework_upstream.h"
#include "grpc_hdr.h"
#include "svk_logger.h"

#define MGMT_FW_NODE_DEFAULT_LOG_FILE "/var/log/svk/svk_mgmt_fw_node.log"
#define MGMT_FW_LOGGER_MODULE_NAME "mgmt_fw_node"
constexpr size_t MGMT_FW_LOGGER_DEFAULT_FILE_COUNT = 10;
// 1MB default max file size
constexpr size_t MGMT_FW_LOGGER_DEFAULT_FILE_SIZE = 1048576ULL;
#define MGMT_FW_LOGGER_DEFAULT_LEVEL "INFO"
#define MGMT_FW_LOGGER_DEFAULT_SINK_TYPE "rotating_file"
#define DEFAULT_CLUSTER_ID "CL_ID_1"
#define DEFAULT_CONTROLLER_ID "localhost"
#define DEFAULT_NODE_NAME "node_1"
#define DEFAULT_CONTROLLER_PORT "9999"
#define DEFAULT_NODE_ID "localhost"
#define DEFAULT_NODE_PORT "9998"

using node_config = struct grpc_node_server_config {
  std::string framework_lib_path;
  std::string framework_conf_file;
  std::string cluster_id;
  std::string controller_id;
  std::string controller_port;
  std::string node_name;
  std::string node_id;
  std::string node_port;
  std::string log_level;
  std::string log_filename;
  std::string log_sink_type;
  int log_file_count;
  uint64_t log_file_size;
};

const std::unordered_map<std::string, level_E> log_level_map = {
    {"TRACE", level_E::TRACE},       {"DEBUG", level_E::DEBUG},
    {"INFO", level_E::INFO},         {"NOTICE", level_E::NOTICE},
    {"WARN", level_E::WARN},         {"ERROR", level_E::ERROR},
    {"CRITICAL", level_E::CRITICAL}, {"ALERT", level_E::ALERT},
    {"FATAL", level_E::FATAL},       {"OFF", level_E::OFF}};

class Servicer : public svk::CommandFwk::Service {
 public:
  explicit Servicer(const std::string &svk_conf_file);
  ~Servicer() override;

  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override;
  const std::string &get_svk_config_node_id() const {
    return m_svk_config.node_id;
  };
  const std::string &get_svk_config_node_port() const {
    return m_svk_config.node_port;
  };
  const node_config &get_svk_config() const { return m_svk_config; };
  bool get_state() const { return m_initialized_flag; };
  void set_server(std::shared_ptr<Server> server) { m_server = server; };
  std::shared_ptr<Server> get_server() const { return m_server; };

 private:
  node_config m_svk_config;
  bool m_initialized_flag = false;
  std::shared_ptr<Server> m_server;
};

std::shared_ptr<Server> Init(Servicer *svcr);
#endif /*__GRPC_SERVER_H__*/