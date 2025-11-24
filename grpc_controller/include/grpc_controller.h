#ifndef __GRPC_CONTROLLER_H__
#define __GRPC_CONTROLLER_H__
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <condition_variable>
#include <mutex>
#include <nlohmann/json.hpp>
#include <queue>
#include <unordered_map>

#include "client_library.h"
#include "events_handler.h"
#include "framework/framework.grpc.pb.h"
#include "framework_struct.h"
#include "framework_upstream.h"
#include "grpc_hdr.h"
#include "node_cmd_helper_fns.h"
#include "sla_hlpr_fns.h"
#include "svk_logger.h"
#include "svk_pub_sub_struct.h"

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
#define API_VERSION "0.1"

#define SVK_NODE_FEATURE_NAME "node"
#define SVK_CXL_FEATURE_NAME "cxl"
#define SLAT_FEATURE_MODULE_NAME "slat"
#define RAS_FEATURE_MODULE_NAME "ras"
#define ME_FEATURE_MODULE_NAME "me"

enum node_status { NODE_ONLINE, NODE_OFFLINE };

const std::map<node_status, std::string> node_status_to_str = {
    {NODE_ONLINE, "online"}, {NODE_OFFLINE, "offline"}};

const std::map<std::string, std::string> command_name_to_desc = {
    {"create_cluster", "Create virtual cluster"},
    {"list_nodes", "List registered nodes "},
    {"list_clusters", "List clusters"},
    {"delete_cluster", "Delete cluster"},
    {"add_node_to_cluster", "Add node to a cluster"},
    {"remove_node_from_cluster", "Remove node from a cluster"}};

std::unique_ptr<Client> CreateClient(const std::string &node_name,
                                     const std::string &node_port);

using controller_config = struct grpc_controller_config {
  std::string controller_id;
  std::string controller_port;
  std::string log_level;
  std::string log_filename;
  std::string log_sink_type;
  int log_file_count;
  uint64_t log_file_size;
};

// Cluster name and list of nodes in cluster
using cluster_info = struct cluster_info {
  std::string cluster_name;
  std::vector<std::string> node_names;
};

// To be stored in db later
using node_info = struct node_info {
  std::string node_name;
  std::string node_ip;
  std::string node_port;
  std::string node_type;
  std::string cluster_name;
  node_status status;  // Online/offline
};

using json = nlohmann::json;

const std::unordered_map<std::string, level_E> ctrl_log_level_map = {
    {"TRACE", level_E::TRACE},       {"DEBUG", level_E::DEBUG},
    {"INFO", level_E::INFO},         {"NOTICE", level_E::NOTICE},
    {"WARN", level_E::WARN},         {"ERROR", level_E::ERROR},
    {"CRITICAL", level_E::CRITICAL}, {"ALERT", level_E::ALERT},
    {"FATAL", level_E::FATAL},       {"OFF", level_E::OFF}};

class ControllerServicer : public svk::Controller::Service {
 public:
  explicit ControllerServicer(const std::string &svk_conf_file);
  ~ControllerServicer() override;
  Status RegisterNode(ServerContext *ctxt, const svk::RegisterRequest *req,
                      svk::RegisterResponse *resp) override;
  Status UnregisterNode(ServerContext *ctxt, const svk::UnregisterRequest *req,
                        svk::UnregisterResponse *resp) override;
  Status SetNodeStatus(ServerContext *ctxt,
                       const svk::SetNodeStatusRequest *req,
                       svk::SetNodeStatusResponse *resp) override;
  Status ProcessControllerCommand(ServerContext *ctxt,
                                  const svk::CommandRequest *req,
                                  svk::CommandResponse *resp) override;
  Status ListClusterNodes(ServerContext *ctxt,
                          const svk::ListClusterCommandRequest *req,
                          svk::ListClusterCommandResponse *resp) override;
  Status ProcessAllocateMemory(const svk::CommandRequest *req,
                               svk::CommandResponse *resp);
  Status ClusterAPI(ServerContext *ctxt, const svk::ClusterRequest *req,
                    svk::ClusterResponse *resp) override;
  Status CreateCluster(const std::string &cluster_name,
                       const std::string &command_params,
                       svk::ClusterResponse *resp);
  Status DeleteCluster(const std::string &cluster_name,
                       svk::ClusterResponse *resp);
  Status ListClusters(svk::ClusterResponse *resp);
  Status ListNodesInCluster(const std::string &cluster_name,
                            svk::ClusterResponse *resp);
  Status AddRemoveNode(const std::string &cluster_name,
                       const std::string &command_name,
                       const std::string &command_params,
                       svk::ClusterResponse *resp);

  Status NodeAPI(ServerContext *ctxt, const svk::NodeRequest *req,
                 svk::NodeResponse *resp) override;
  Status ListNodes(svk::NodeResponse *resp);

  Status FeatureAPI(ServerContext *ctxt, const svk::FeatureRequest *req,
                    svk::FeatureResponse *resp) override;
  Status EventAPI(ServerContext *ctxt, const svk::EventRequest *req,
                  svk::EventResponse *resp) override;
  Status SLAManagementAPI(ServerContext *ctxt,
                          const svk::SLAManagementRequest *req,
                          svk::SLAManagementResponse *resp) override;
  Status StatsAPI(ServerContext *ctxt, const svk::StatsRequest *req,
                  svk::StatsResponse *resp) override;
  int HlprGetNodeDetails(std::string const &node_name, std::string &node_port,
                         std::string &cluster_name, std::string &node_ip);

  const std::string &get_svk_config_controller_id() {
    return m_svk_config.controller_id;
  };

  const std::string &get_svk_config_controller_port() {
    return m_svk_config.controller_port;
  };
  const controller_config &get_svk_config() const { return m_svk_config; };
  bool get_state() const { return m_initialized_flag; };
  void set_server(std::shared_ptr<Server> server) { m_server = server; };
  std::shared_ptr<Server> get_server() const { return m_server; };
  void set_config_changed(bool state) { m_config_changed = state; };
  bool is_config_changed() const { return m_config_changed; };
  std::unordered_map<std::string, std::unordered_map<std::string, std::string>>
  get_cluster_map() const {
    return m_cluster_map;
  };

  void set_cluster_map(
      const std::unordered_map<std::string,
                               std::unordered_map<std::string, std::string>>
          &cluster_map) {
    m_cluster_map = cluster_map;
  }

  bool get_stop_flag() const { return stop_flag; };
  void set_stop_flag() { stop_flag = true; };
  void set_zmq_socket(void *zmq_context, void *zmq_socket) {
    m_zmq_subscriber_socket = zmq_socket;
    m_zmq_subscriber_context = zmq_context;
  };
  void *get_zmq_context() { return m_zmq_subscriber_context; };
  void *get_zmq_socket() { return m_zmq_subscriber_socket; };

  // Queue operations
  void insert_event_to_queue(json event_data) {
    std::scoped_lock lock(m_event_q_mutex);
    m_event_queue.push(std::move(event_data));
    m_event_q_cond_var.notify_one();  // Notify one waiting thread
  };

  // Remove event from queue if available
  //  Otherwise returns -1 if empty for 2 seconds
  int remove_event_from_queue(json &event_data) {
    std::unique_lock lock(m_event_q_mutex);
    m_event_q_cond_var.wait_for(lock, std::chrono::seconds(2), [this]() {
      return (!m_event_queue.empty() || this->get_stop_flag());
    });
    if (m_event_queue.empty()) {
      return -1;
    }
    event_data = std::move(m_event_queue.front());
    m_event_queue.pop();
    return 0;
  }

  bool check_event_queue_empty() const { return m_event_queue.empty(); }

 protected:
  Status SetAppSLACommand(const std::string &cluster_name,
                          const std::string &node_names,
                          const std::string &command_params_str,
                          std::string &output);

 private:
  nlohmann::json ClusterResponseJson(std::string cluster_name);
  Status GetDevicesWithSLAInfo(const std::vector<std::string> &node_names,
                               std::string &output);
  // Return the node_info for the given node name
  int GetNodeInfo(const std::string &node_name, node_info &node_info) {
    if (m_registered_nodes.find(node_name) == m_registered_nodes.end()) {
      return -1;
    }
    node_info = m_registered_nodes[node_name];
    return 0;
  };
  controller_config m_svk_config;
  bool m_initialized_flag = false;
  // A cluster map with the cluster name to the map of <node_name, port>,
  // maintaining for backwards compatibility for now
  std::unordered_map<std::string, std::unordered_map<std::string, std::string>>
      m_cluster_map;
  // Map of clusters <cluster_name, cluster_info>
  std::unordered_map<std::string, cluster_info> m_cluster_info;
  // Map of registered nodes, may or may not be part of a cluster
  std::unordered_map<std::string, node_info> m_registered_nodes;
  std::shared_ptr<Server> m_server;
  bool m_config_changed = false;
  bool stop_flag = false;
  // Store the ZMQ subscriber socket and context
  void *m_zmq_subscriber_socket = nullptr;
  void *m_zmq_subscriber_context = nullptr;

  // Queue for storing and retrieving the events
  std::queue<json> m_event_queue;
  mutable std::mutex m_event_q_mutex;
  std::condition_variable m_event_q_cond_var;
};

#endif /*__GRPC_CONTROLLER_H__*/
