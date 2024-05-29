#ifndef __GRPC_CONTROLLER_H__
#define __GRPC_CONTROLLER_H__
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <unordered_map>

#include "framework/framework.grpc.pb.h"
#include "framework_struct.h"
#include "framework_upstream.h"
#include "grpc_hdr.h"
#include "svk_logger.h"

#define CONTROLLER_CONF_SECTION_TAG "svk_mgmt_fw_controller"
#define CONTROLLER_NODE_DEFAULT_LOG_FILE \
  "/var/log/svk/svk_mgmt_fw_controller.log"
#define CONTROLLER_LOGGER_MODULE_NAME "controller"
#define CONTROLLER_LOGGER_DEFAULT_FILE_COUNT 10
#define CONTROLLER_LOGGER_DEFAULT_FILE_SIZE \
  1048576ULL  // 1MB default max file size
#define CONTROLLER_LOGGER_DEFAULT_LEVEL "INFO"
#define CONTROLLER_LOGGER_DEFAULT_SINK_TYPE "rotating_file"
#define CONTROLLER_DEFAULT_ID "localhost"
#define CONTROLLER_DEFAULT_PORT "9999"

using controller_config = struct grpc_controller_config {
  std::string controller_id;
  std::string controller_port;
  std::string log_level;
  std::string log_filename;
  std::string log_sink_type;
  int log_file_count;
  uint64_t log_file_size;
};

const std::unordered_map<std::string, level_E> ctrl_log_level_map = {
    {"TRACE", level_E::TRACE},       {"DEBUG", level_E::DEBUG},
    {"INFO", level_E::INFO},         {"NOTICE", level_E::NOTICE},
    {"WARN", level_E::WARN},         {"ERROR", level_E::ERROR},
    {"CRITICAL", level_E::CRITICAL}, {"ALERT", level_E::ALERT},
    {"FATAL", level_E::FATAL},       {"OFF", level_E::OFF}};

class ControllerServicer : public svk::Controller::Service {
 public:
  explicit ControllerServicer(const std::string &svk_conf_file);
  ~ControllerServicer();
  Status RegisterNode(ServerContext *ctxt, const svk::RegisterRequest *req,
                      svk::RegisterResponse *resp) override;
  Status UnregisterNode(ServerContext *ctxt, const svk::UnregisterRequest *req,
                        svk::UnregisterResponse *resp) override;
  Status ProcessControllerCommand(ServerContext *ctxt,
                                  const svk::CommandRequest *req,
                                  svk::CommandResponse *resp) override;
  const std::string &get_svk_config_controller_id() {
    return m_svk_config.controller_id;
  };
  const std::string &get_svk_config_controller_port() {
    return m_svk_config.controller_port;
  };
  const controller_config &get_svk_config() { return m_svk_config; };
  const bool get_state() { return m_initialized_flag; };
  void set_server(std::shared_ptr<Server> server) { m_server = server; };
  std::shared_ptr<Server> get_server() { return m_server; };

 private:
  controller_config m_svk_config;
  bool m_initialized_flag = false;
  std::unordered_map<std::string, std::unordered_map<std::string, std::string>>
      m_cluster_map;
  std::shared_ptr<Server> m_server;
};

#endif /*__GRPC_CONTROLLER_H__*/