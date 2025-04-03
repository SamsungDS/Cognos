#include "grpc_controller.h"

#include <csignal>
#include <set>
#include <thread>
#include <zmq.hpp>

#include "client_library.h"
#include "sla_hlpr_fns.h"
#include "svk_zmq_api.h"
#define MAX_SIZE 4096

#ifndef BUILD_TESTING
ABSL_FLAG(std::string, svk_conf_file, "", "svk configuration file to read");
#endif

using namespace svk;

std::atomic<int> gSignalStatus = -1;

const std::unique_ptr<SLADeviceHelper> g_sla_device_hlpr =
    std::make_unique<SLADeviceHelper>(SLA_CONFIG_FILE);

int tokenize(std::string node_id_list, std::set<std::string> &tokens) {
  int count = 0;
  char *s = (char *)node_id_list.c_str();
  char *tok = strtok(s, ",");
  while (tok != NULL) {
    tokens.insert(tok);
    count++;
    tok = strtok(NULL, ",");
  }
  return count;
}

int initialize_logger(const controller_config &config) {
  int status = -1;
  auto found = ctrl_log_level_map.find(config.log_level);
  if (found == ctrl_log_level_map.end()) {
    std::cout << "Matching log level for the [" << config.log_level
              << "] not found. Exiting" << std::endl;
    return status;
  }

  if (svk_logger_init(CONTROLLER_LOGGER_MODULE_NAME,
                      config.log_filename.c_str(), found->second,
                      config.log_file_count, config.log_file_size,
                      config.log_sink_type.c_str()) == 0) {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               "Mgmt FW Controller logger is initialized");
    status = 0;
  } else {
    std::cout << "Mgmt FW Controller logger initialization failed" << std::endl;
  }
  return status;
}

int read_svk_conf_file(const std::string svk_conf_file,
                       controller_config *config) {
  int status = -1;
  namespace pt = boost::property_tree;

  try {
    pt::ptree root;
    pt::read_json(svk_conf_file, root);
    pt::ptree mgmt_config_pt = root.get_child(CONTROLLER_CONF_SECTION_TAG);

    config->controller_id =
        mgmt_config_pt.get("controller.id", CONTROLLER_DEFAULT_ID);
    config->controller_port = mgmt_config_pt.get<std::string>(
        "controller.port", CONTROLLER_DEFAULT_PORT);

    try {
      pt::ptree logger_info_pt = mgmt_config_pt.get_child("logger");
      config->log_level = logger_info_pt.get<std::string>(
          "log_level", CONTROLLER_LOGGER_DEFAULT_LEVEL);
      config->log_filename = logger_info_pt.get<std::string>(
          "log_file_name", CONTROLLER_NODE_DEFAULT_LOG_FILE);
      config->log_file_count = logger_info_pt.get<uint64_t>(
          "log_file_count", CONTROLLER_LOGGER_DEFAULT_FILE_COUNT);
      config->log_file_size = logger_info_pt.get<uint64_t>(
          "log_file_size", CONTROLLER_LOGGER_DEFAULT_FILE_SIZE);
      config->log_sink_type = logger_info_pt.get<std::string>(
          "sink_type", CONTROLLER_LOGGER_DEFAULT_SINK_TYPE);
    } catch (std::exception &e) {
      std::cout
          << "Unable to read Logger section of Mgmt FW in SVK config. Error -> "
          << e.what() << std::endl;
      // Use defaults
      config->log_level = "INFO";
      config->log_filename = CONTROLLER_NODE_DEFAULT_LOG_FILE;
      config->log_file_count = CONTROLLER_LOGGER_DEFAULT_FILE_COUNT;
      config->log_file_size = CONTROLLER_LOGGER_DEFAULT_FILE_SIZE;
      config->log_sink_type = "rotating_file";
    }
    status = 0;
  } catch (std::exception &e) {
    std::cerr << "Unable to read SVK config. Error -> " << e.what()
              << std::endl;
  }

  return status;
}

int update_node_status_from_str(std::string status_str, node_status &status) {
  for (const auto &pair : node_status_to_str) {
    if (pair.second == status_str) {
      status = pair.first;
      return 0;
    }
  }
  return -1;
}

ControllerServicer::ControllerServicer(const std::string &svk_conf_file) {
  struct stat buf;
  int ret_val = -1;
  controller_config config;
  std::string logger_str;

  if (stat(svk_conf_file.c_str(), &buf) != 0 ||
      (buf.st_mode & S_IFMT) != S_IFREG) {
    std::cout << "Invalid path given for config file - " << svk_conf_file
              << std::endl;
    return;
  }

  ret_val = read_svk_conf_file(svk_conf_file, &config);
  if (ret_val < 0) {
    std::cout << "Failed to read config file - " << svk_conf_file << std::endl;
    return;
  }

  ret_val = initialize_logger(config);
  if (ret_val < 0) {
    std::cout << "Failed to create logger " << std::endl;
    return;
  }

  m_svk_config = config;

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "Controller servicer initialized");

  m_initialized_flag = true;
}

ControllerServicer::~ControllerServicer() {
  auto server = this->get_server();

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "Shutting down the gRPC Controller server");
  server->Shutdown();
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "gRPC Controller server is shutdown");
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "Closing the logger instance as part of shutdown");

  svk_logger_close(CONTROLLER_LOGGER_MODULE_NAME);

  return;
}

/**
 * @brief Creates a json object which contains a list of nodes in the given
 * cluster. The returned json object will look like this:
 * {"cluster_name":"cluster1","nodes":[{"node_name":"test_node1"},{"node_name":"test_node2"}]}
 *
 * @param cluster_name cluster to get the list of nodes for
 * @return nlohmann::json json object containing the list of nodes in the
 * cluster
 */
nlohmann::json ControllerServicer::ClusterResponseJson(
    std::string cluster_name) {
  using json = nlohmann::json;
  json cluster_nodes_resp;
  cluster_info cluster = m_cluster_info.at(cluster_name);
  json node_list = json::array();
  for (auto &node_name : cluster.node_names) {
    json single_node;
    single_node["node_name"] = node_name;
    single_node["status"] =
        node_status_to_str.at(m_registered_nodes.at(node_name).status);
    node_list.push_back(single_node);
  }
  cluster_nodes_resp["cluster_name"] = cluster_name;
  cluster_nodes_resp["nodes"] = node_list;
  return cluster_nodes_resp;
}

Status ControllerServicer::RegisterNode(ServerContext *ctxt,
                                        const svk::RegisterRequest *req,
                                        svk::RegisterResponse *resp) {
  std::string node_name = req->node_name();
  std::string node_ip = req->node_ip();
  std::string node_port = req->node_port();
  std::string cluster_name = req->cluster_name();

  node_info node;
  std::string logger_str;
  int status = -1;
  int device_info_status;

  logger_str =
      "RegisterNode called with node_name:" + node_name + " node_ip:" + node_ip;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  if (node_ip.length() == 0 || node_port.length() == 0) {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               "Invalid input. One of the arguments is zero length");
    resp->set_error_id_or_string_if_any(
        "One of the input parameters (node_name/node_ip/node_port) is of zero "
        "length");
    resp->set_error_code(status);
    return Status(grpc::INVALID_ARGUMENT,
                  "Invalid input - zero length arg given");
  }

  node.node_ip = node_ip;
  node.node_port = node_port;
  node_name.length() > 0 ? node.node_name = node_name
                         : node.node_name = node_ip;
  node.cluster_name = "";
  node.status = NODE_ONLINE;

  bool node_exists = false;
  for (const auto &curr_node : m_registered_nodes) {
    if (curr_node.second.node_name == node.node_name) {
      // Node already registered, coming online
      m_registered_nodes[curr_node.second.node_name].status = NODE_ONLINE;
      node_exists = true;
      logger_str = "Node " + curr_node.second.node_name +
                   " is already registered with the "
                   "controller, coming online";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
      break;
    }
  }
  // Node not registered yet, add to map
  if (!node_exists) {
    m_registered_nodes.insert(std::make_pair(node.node_name, node));
    logger_str = "Registered the node " + node.node_name + " with controller.";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
  }

  // If cluster_name is given, add to old m_cluster_map for backwards
  // compatibility
  if (cluster_name.length() != 0) {
    logger_str = "cluster_name given in node_register request";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    if (m_cluster_info.find(cluster_name) == m_cluster_info.end()) {
      logger_str = "Registering the cluster_name: " + cluster_name;
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
      // Update old cluster map
      m_cluster_map[cluster_name][node_ip] = node_port;
      // Update new cluster map
      m_cluster_info[cluster_name].node_names.push_back(node.node_name);
      logger_str = "Registered the node_id " + node_ip + ":" + node_port +
                   " with cluster:" + cluster_name;
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
    } else {
      logger_str =
          "Found the cluster_name: " + cluster_name + " already registered";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());

      if (m_cluster_map[cluster_name].find(node_ip) ==
          m_cluster_map[cluster_name].end()) {
        // Update old cluster map
        m_cluster_map[cluster_name][node_ip] = node_port;
        // Update new cluster map
        m_cluster_info[cluster_name].node_names.push_back(node.node_name);
        logger_str = "Registered the node_id " + node_ip + ":" + node_port +
                     " with cluster:" + cluster_name;
        svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                   logger_str.c_str());
      } else {
        logger_str = "Node with node_id " + node_ip + ":" + node_port +
                     " already registered";
        svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                   logger_str.c_str());
      }
    }
  }

  device_info_status = g_sla_device_hlpr->GetDeviceInfo(node_ip, node_port);
  if (device_info_status != 0) {
    return Status(grpc::UNKNOWN, "Failed to get devices");
  }
  m_config_changed = true;
  status = 0;
  resp->set_error_code(status);
  return Status::OK;
}

Status ControllerServicer::UnregisterNode(ServerContext *ctxt,
                                          const svk::UnregisterRequest *req,
                                          svk::UnregisterResponse *resp) {
  std::string cluster_id = req->cluster_id();
  std::string node_id = req->node_id();
  std::string node_port = req->node_port();
  std::string logger_str;
  int status = -1;

  logger_str = "UnregisterNode called with cluster_id:" + cluster_id +
               " node_id:" + node_id;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  if (cluster_id.length() == 0 || node_id.length() == 0) {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               "Invalid input. One of the arguments is zero length");
    return Status(grpc::INVALID_ARGUMENT,
                  "Invalid input - zero length arg given");
  }

  if (m_cluster_map.find(cluster_id) == m_cluster_map.end()) {
    logger_str = "Unregistering the cluster_id: " + cluster_id + " not found";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());

    return Status(grpc::INVALID_ARGUMENT, "cluster_id not found");
  }
  logger_str = "Found the registered cluster_id: " + cluster_id;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  logger_str = "Checking the node_id: " + node_id;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  if (m_cluster_map[req->cluster_id()].find(node_id) ==
      m_cluster_map[req->cluster_id()].end()) {
    logger_str = "Node with node_id " + node_id + " not found";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return Status(grpc::INVALID_ARGUMENT, "node_id not found");
  } else {
    logger_str = "Found Node with node_id " + node_id;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());

    int count = m_cluster_map[cluster_id].erase(node_id);
    if (count == 1) {
      logger_str = "Unregistered the node_id " + node_id + " successfully";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
      status = 0;
    }
  }
  status = g_sla_device_hlpr->UnregisterDevicesForNode(node_id);
  if (status != 0) {
    logger_str =
        "Failed to remove devices from the SLA tracker for the node_id " +
        node_id;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    return Status(grpc::INVALID_ARGUMENT,
                  "Failed to remove devices from the SLA tracker for the node");
  }
  m_config_changed = true;
  resp->set_status("Success");
  resp->set_error_code(status);

  return Status::OK;
}

Status ControllerServicer::SetNodeStatus(ServerContext *ctxt,
                                         const svk::SetNodeStatusRequest *req,
                                         svk::SetNodeStatusResponse *resp) {
  std::string logger_str;

  std::string node_name = req->node_name();
  std::string node_status = req->node_status();

  if (node_name.length() == 0 || node_status.length() == 0) {
    logger_str = "Invalid node name or status";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any(logger_str);
    resp->set_error_code(SVK_STATUS_FAIL);
    return Status(grpc::INVALID_ARGUMENT, logger_str);
  }

  auto node_itr = m_registered_nodes.find(node_name);
  if (node_itr == m_registered_nodes.end()) {
    logger_str = "Node " + node_name + " not found";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any(logger_str);
    resp->set_error_code(SVK_STATUS_FAIL);
    return Status(grpc::INVALID_ARGUMENT, logger_str);
  }
  node_info &node_to_update = node_itr->second;
  int status = update_node_status_from_str(node_status, node_to_update.status);
  if (status) {
    logger_str = "Invalid status given: " + node_status +
                 ". Could not update node status.";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any(logger_str);
    resp->set_error_code(SVK_STATUS_FAIL);
    return Status(grpc::INVALID_ARGUMENT, logger_str);
  }
  logger_str = "Updated node " + node_name + "'s status to " +
               node_status_to_str.at(node_to_update.status);
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  return Status::OK;
}

Status ControllerServicer::ProcessAllocateMemory(const svk::CommandRequest *req,
                                                 svk::CommandResponse *resp) {
  Status cmd_status;
  svk::CommandRequest req_node;
  svk::CommandResponse resp_node;
  std::string logger_str;
  std::string feature_params;
  uint64_t sla_latency_ns;
  uint64_t size;
  char app_name[128];
  char logic_module[128];
  std::vector<DeviceInfo> app_devices;
  int status = -1;

  feature_params = req->feature_params();

  char *ptr_sla = strstr((char *)feature_params.c_str(), "sla_latency_ns");
  char *ptr_app = strstr((char *)feature_params.c_str(), "app_name");
  char *ptr_size = strstr((char *)feature_params.c_str(), "size");
  char *ptr_logicmod = strstr((char *)feature_params.c_str(), "logic_module");
  if (ptr_sla == nullptr || ptr_app == nullptr || ptr_size == nullptr) {
    logger_str =
        "ProcessControllerCommand called for allocate_memory without "
        "sla_latency_ns, size, logic_module or app_name in params";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return Status(grpc::INVALID_ARGUMENT, "invalid feature params");
  }

  sscanf(ptr_sla, "sla_latency_ns=%lu", &sla_latency_ns);
  sscanf(ptr_app, "app_name=%[a-zA-Z0-9]", &app_name[0]);
  if (ptr_logicmod) {
    sscanf(ptr_logicmod, "logic_module=%[a-zA-Z0-9]", &logic_module[0]);
  }
  sscanf(ptr_size, "size=%lu", &size);
  status = g_sla_device_hlpr->GetDeviceForAppRequirements(sla_latency_ns, size,
                                                          app_devices);
  if (status != 0) {
    logger_str =
        "ProcessControllerCommand allocate_memory failed in getting devices "
        "for the given SLA";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return Status(grpc::INVALID_ARGUMENT, "devices not met SLA");
  }

  for (auto itr = m_cluster_map[req->cluster_id()].begin();
       itr != m_cluster_map[req->cluster_id()].end(); ++itr) {
    std::string device_names = "";
    std::string device_latency_str = "";
    std::string node_name;
    std::string port;
    logger_str = "Checking for devices in the node " + itr->first +
                 " in the cluster " + req->cluster_id();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());

    node_name = itr->first;
    port = itr->second;

    for (auto dev : app_devices) {
      if (dev.node_name == node_name) {
        if (device_names.length() == 0) {
          device_names = "devices=" + std::to_string(dev.numa);
          device_latency_str = "device_sla_latency_ns=" +
                               std::to_string(dev.device_qos.avg_latency_ns);
        } else {
          device_names += "," + std::to_string(dev.numa);
          device_latency_str +=
              "," + std::to_string(dev.device_qos.avg_latency_ns);
        }
      }
    }

    if (device_names.length() != 0) {
      req_node.set_node_id(node_name);
      req_node.set_feature_id(feature_id::SLA_TRACKER);
      feature_params = "app_name=" + std::string(app_name) + ";" +
                       "app_sla_latency_ns=" + std::to_string(sla_latency_ns) +
                       ";" + device_names + ";" + device_latency_str +
                       ";host_name=" + node_name;
      if (ptr_logicmod) {
        feature_params += ";logic_module=" + std::string(logic_module);
      }
      req_node.set_feature_params(feature_params);
      logger_str = "Command with feature_params " + feature_params +
                   " is passed to node " + node_name;
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());

      Client client(node_name, port);
      cmd_status = client.ProcessNodeCommand(&req_node, &resp_node);
      if (cmd_status.ok() != true) {
        // If one of the nodes return failure for whatever reason, we are
        // returning error for the whole cluster. Need to handle partial
        // failures accordingly
        logger_str = "ProcessNodeCommand with feature_params " +
                     feature_params + " failed for node " + node_name;
        svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                   logger_str.c_str());

        return cmd_status;
      }
    }
  }

  App_Device_List app_device_data;
  app_device_data.appLatencyns = sla_latency_ns;
  app_device_data.size = size;
  for (auto dev : app_devices) {
    app_device_data.device_info.push_back(dev);
  }
  g_sla_device_hlpr->SetSLADataForApp(app_name, app_device_data);

  logger_str = "ProcessAllocateMemory processed successfully";
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());
  return Status::OK;
}

Status ControllerServicer::ProcessControllerCommand(
    ServerContext *ctxt, const svk::CommandRequest *req,
    svk::CommandResponse *resp) {
  Status status;
  svk::CommandRequest req_node;
  svk::CommandResponse resp_node;
  std::string logger_str;
  std::string feature_params;
  uint64_t feature_id;

  if (req->cluster_id().length() == 0 || req->feature_params().length() == 0) {
    logger_str = "ProcessControllerCommand called for feature_id <" +
                 std::to_string(req->feature_id()) + "> with params <" +
                 req->feature_params() + "> on nodes <" + req->node_id() +
                 "> - zero length args";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return Status(
        grpc::INVALID_ARGUMENT,
        "Args (cluster_id/feature_id/feature_params) is of zero length");
  }

  if (m_cluster_map[req->cluster_id()].size() == 0) {
    logger_str = "ProcessControllerCommand called for cluster_id " +
                 req->cluster_id() + " not found";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return Status(grpc::INVALID_ARGUMENT, "cluster_id not found");
  }

  std::set<std::string> nodes;
  int count = 0;

  if (req->node_id().length()) {
    count = tokenize(req->node_id(), nodes);
    for (auto itr = nodes.begin(); itr != nodes.end(); ++itr) {
      if (m_cluster_map[req->cluster_id()].find(*itr) ==
          m_cluster_map[req->cluster_id()].end()) {
        logger_str = "ProcessControllerCommand called for node_id " + *itr +
                     "is not part of cluster_id " + req->cluster_id();
        svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                   logger_str.c_str());
        return Status(grpc::INVALID_ARGUMENT, "node_id not part of cluster");
      }
    }
  }

  feature_id = req->feature_id();
  feature_params = req->feature_params();

  if (req->command_id().size() != 0) {
    if (req->command_id() == "allocate_memory") {
      logger_str = "ProcessAllocateMemory called";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());

      status = ProcessAllocateMemory(req, resp);
      return status;
    }
  }

  for (auto itr = m_cluster_map[req->cluster_id()].begin();
       itr != m_cluster_map[req->cluster_id()].end(); ++itr) {
    if (count && nodes.find(itr->first) == nodes.end()) {
      continue;
    }
    req_node.set_node_id(itr->first);
    req_node.set_feature_id(feature_id);
    req_node.set_feature_params(feature_params);
    Client client(itr->first, m_cluster_map[req->cluster_id()][itr->first]);
    status = client.ProcessNodeCommand(&req_node, &resp_node);
    if (status.ok() == true) {
      CommandResponse_NodeResponse *response = resp->add_node_responses();
      response->set_output(resp_node.node_responses(0).output());
      response->set_node_id(resp_node.node_responses(0).node_id());
    } else {
      // If one of the nodes return failure for whatever reason, we are
      // returning error for the whole cluster. Need to handle partial failures
      // accordingly
      return status;
    }
  }
  return Status::OK;
}

Status ControllerServicer::ListClusterNodes(
    ServerContext *ctxt, const svk::ListClusterCommandRequest *req,
    svk::ListClusterCommandResponse *resp) {
  Status status;

  if (req->cluster_id().length() != 0) {
    if (m_cluster_map.find(req->cluster_id()) == m_cluster_map.end()) {
      std::string logger_str;
      logger_str = "ListClusterNodes called for cluster_id " +
                   req->cluster_id() + " not found";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                 logger_str.c_str());
      return Status(grpc::INVALID_ARGUMENT, "cluster_id not found");
    }
    ListClusterCommandResponse_ClusterDetails *cluster_info =
        resp->add_cluster_info();
    cluster_info->set_cluster_id(req->cluster_id());
    for (auto itr = m_cluster_map[req->cluster_id()].begin();
         itr != m_cluster_map[req->cluster_id()].end(); ++itr) {
      NodeDetails *node_info = cluster_info->add_node_info();
      node_info->set_node_id(itr->first);
      node_info->set_node_port(m_cluster_map[req->cluster_id()][itr->first]);
    }
  } else {
    for (auto cluster_itr = m_cluster_map.begin();
         cluster_itr != m_cluster_map.end(); cluster_itr++) {
      ListClusterCommandResponse_ClusterDetails *cluster_info =
          resp->add_cluster_info();
      cluster_info->set_cluster_id(cluster_itr->first);
      for (auto node_itr = cluster_itr->second.begin();
           node_itr != cluster_itr->second.end(); ++node_itr) {
        NodeDetails *node_info = cluster_info->add_node_info();
        node_info->set_node_id(node_itr->first);
        node_info->set_node_port(node_itr->second);
      }
    }
  }
  return Status::OK;
}

Status ControllerServicer::CreateCluster(std::string cluster_name,
                                         std::string command_params,
                                         svk::ClusterResponse *resp) {
  std::string logger_str;
  cluster_info clstr_info;
  Status status;

  if (cluster_name.length() == 0 || command_params.length() == 0) {
    logger_str = "Cluster command called with invalid parameters";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               "Invalid request parameters for CreateCluster");
    resp->set_error_id_or_string_if_any(
        "Invalid request parameters for CreateCluster");
    resp->set_error_code(SVK_STATUS_FAIL);
    return Status(grpc::INVALID_ARGUMENT,
                  "Invalid request parameters for CreateCluster");
  }

  using json = nlohmann::json;

  try {
    auto it = m_cluster_info.find(cluster_name);
    if (it != m_cluster_info.end()) {
      logger_str = "Cluster id " + cluster_name + " already exists";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                 logger_str.c_str());
      status = Status(grpc::ALREADY_EXISTS, "Cluster id already exists");
      clstr_info = m_cluster_info[cluster_name];
    } else {
      // Create a new cluster with nodes in command_params
      // Go through each node in command_params add to cluster
      // Expecting proper json string format, fail if can't parse

      json j = json::parse(command_params);

      json node = j["nodes"];
      if (node.empty()) {
        logger_str = "No nodes found in command_params";
        svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                   logger_str.c_str());
        return Status(grpc::INVALID_ARGUMENT,
                      "No nodes found in command_params");
      }
      for (auto &[key, value] : node.items()) {
        std::string node_name = value["node_name"];
        bool node_added = false;
        // Add node to cluster if node exists and is online
        if (m_registered_nodes.count(node_name)) {
          node_info n = m_registered_nodes[node_name];
          if (n.status == NODE_ONLINE) {
            clstr_info.cluster_name = cluster_name;
            clstr_info.node_names.push_back(node_name);

            // Backward compatibility
            m_cluster_map[cluster_name][n.node_ip] = n.node_port;
            n.cluster_name = cluster_name;
            m_registered_nodes[node_name] = n;
            node_added = true;
          }
        }
        if (!node_added) {
          logger_str =
              "Node " + node_name +
              " is offline or not registered, could not be added to cluster";
          svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                     logger_str.c_str());
          m_cluster_map.erase(cluster_name);
          resp->set_error_id_or_string_if_any(logger_str);
          resp->set_error_code(SVK_STATUS_FAIL);
          return Status(grpc::INVALID_ARGUMENT, logger_str);
        }
      }
      m_cluster_info[cluster_name] = clstr_info;
      logger_str = "Cluster id " + cluster_name + " created";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
      status = Status::OK;
    }
    // Create response with nodes in the cluster
    json cluster = json::array();
    json nodes_in_cluster = ClusterResponseJson(cluster_name);
    cluster.push_back(nodes_in_cluster);
    json response;
    response["clusters"] = cluster;

    resp->set_command_response(response.dump());
    resp->set_error_code(SVK_STATUS_SUCCESS);
  } catch (json::exception &e) {
    std::string exception_str = e.what();
    logger_str = "JSON error: " + exception_str;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any("Error parsing json command_params");
    resp->set_error_code(SVK_STATUS_FAIL);
    return Status(grpc::INVALID_ARGUMENT, "Error parsing json command_params");
  }
  return status;
}

/**
 * Deletes the specified cluster.
 *
 * @param cluster_name The name of the cluster to delete.
 * @param resp A pointer to the ClusterResponse object to store the information
 * of deleted cluster.
 * @return Status indicating the success or failure of the operation.
 */
Status ControllerServicer::DeleteCluster(std::string cluster_name,
                                         svk::ClusterResponse *resp) {
  std::vector<std::string> node_names;
  node_info node;
  std::string logger_str;

  // If cluster_name is empty, return invalid argument error.
  if (cluster_name.length() == 0) {
    logger_str =
        "Invalid request parameters for DeleteCluster: cluster_name is null.";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any(logger_str.c_str());
    resp->set_error_code(SVK_STATUS_FAIL);
    return Status(grpc::INVALID_ARGUMENT, logger_str.c_str());
  }

  // Find the cluster by the given cluster_name
  // If not found, return invalid argument error.
  if (m_cluster_info.find(cluster_name) == m_cluster_info.end()) {
    logger_str =
        "Invalid request parameters for DeleteCluster: " + cluster_name +
        " not found in deletion";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any(logger_str.c_str());
    resp->set_error_code(SVK_STATUS_FAIL);
    return Status(grpc::INVALID_ARGUMENT, logger_str.c_str());
  }

  // Iterate over all nodes in the cluster and remove the cluster_name in
  // node_info
  node_names = m_cluster_info[cluster_name].node_names;
  for (auto &node_name : node_names) {
    node = m_registered_nodes[node_name];
    node.cluster_name = "";
    logger_str = "Node " + node.node_name + " changes its cluster_name to " +
                 ((node.cluster_name == "") ? "null" : node.cluster_name) + ".";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::DEBUG,
               logger_str.c_str());
  }
  // Update m_cluster_info table
  // Only remove the mapping from cluster_name to node lists. Keep the node
  // status as registered.
  m_cluster_info.erase(cluster_name);

  // Backward compatibility
  m_cluster_map.erase(cluster_name);

  resp->set_error_code(SVK_STATUS_SUCCESS);

  logger_str = "Cluster " + cluster_name + " removed.";
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  return Status::OK;
}

/**
 * This function returns a JSON array of cluster names in a string in a format
 * of {clusters: [cluster_name_0, cluster_name_1] }.
 *
 * @param resp A pointer to svk::ClusterResponse object to store the response.
 *
 * @return Status object indicating the status of the operation.
 */
Status ControllerServicer::ListClusters(svk::ClusterResponse *resp) {
  Status status;
  std::string cluster_name;
  using json = nlohmann::json;
  json cluster_names = nlohmann::json::array();
  json clusters_info;

  status = Status::OK;

  // Iterate through the m_cluster_info and add each cluster name to the
  // cluster_names array.

  for (const auto &it : m_cluster_info) {
    cluster_name = it.first;
    json name_json;
    name_json["cluster_name"] = cluster_name;
    cluster_names.push_back(name_json);
  }

  // Construct the response JSON object.
  clusters_info["clusters"] = cluster_names;

  // Set the command response in the resp object.
  resp->set_command_response(clusters_info.dump());

  std::string logger_str = "ListClusters returns " +
                           std::to_string(std::size(cluster_names)) +
                           " cluster names";
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());
  resp->set_error_code(SVK_STATUS_SUCCESS);
  return status;
}

Status ControllerServicer::ListNodesInCluster(std::string cluster_name,
                                              svk::ClusterResponse *resp) {
  std::string logger_str;
  if (cluster_name.length() == 0) {
    logger_str = "ListNodesInCluster called with empty cluster name";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any(logger_str);
    resp->set_error_code(SVK_STATUS_FAIL);
    return Status(grpc::INVALID_ARGUMENT, logger_str);
  }

  const auto &cluster = m_cluster_info.find(cluster_name);
  if (cluster != m_cluster_info.end()) {
    using json = nlohmann::json;
    json resp_json;
    json cluster_json = json::array();
    cluster_json.push_back(ClusterResponseJson(cluster_name));
    resp_json["clusters"] = cluster_json;

    logger_str = "Listed " + std::to_string(cluster->second.node_names.size()) +
                 " nodes in cluster " + cluster_name;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    resp->set_error_code(SVK_STATUS_SUCCESS);
    resp->set_command_response(resp_json.dump());
    return Status::OK;
  } else {
    logger_str = "Cluster " + cluster_name + " not found";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any(logger_str);
    resp->set_error_code(SVK_STATUS_FAIL);
    return Status(grpc::NOT_FOUND, logger_str);
  }
}

// Combining add and remove node from cluster to prevent duplicate code
Status ControllerServicer::AddRemoveNode(std::string cluster_name,
                                         std::string command_name,
                                         std::string command_params,
                                         svk::ClusterResponse *resp) {
  Status status;
  std::string logger_str;

  if (cluster_name.length() == 0 || command_params.length() == 0) {
    logger_str =
        command_name + " called with no cluster_name or command_params";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any(logger_str);
    resp->set_error_code(SVK_STATUS_FAIL);
    return Status(grpc::INVALID_ARGUMENT, logger_str);
  }

  using json = nlohmann::json;
  try {
    // Parse command_params for nodes
    json params_json = json::parse(command_params);

    json nodes = params_json["nodes"];
    if (nodes.empty()) {
      logger_str = command_name + " called with empty nodes list";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                 logger_str.c_str());
      resp->set_error_id_or_string_if_any(logger_str);
      resp->set_error_code(SVK_STATUS_FAIL);
      return Status(grpc::INVALID_ARGUMENT, logger_str);
    }
    // Add or remove given nodes from cluster
    for (auto &[key, value] : nodes.items()) {
      std::string node_name = value["node_name"];
      // Add or remove node if node is registered and cluster exists
      if (m_registered_nodes.count(node_name) &&
          m_cluster_info.count(cluster_name)) {
        node_info &curr_node = m_registered_nodes[node_name];
        // Add node to cluster
        if (command_name == "add_node_to_cluster") {
          if (curr_node.cluster_name.length() != 0) {
            logger_str = "Node " + node_name + " is already part of a cluster.";

            svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                       logger_str.c_str());
            resp->set_error_id_or_string_if_any(logger_str);
            resp->set_error_code(SVK_STATUS_FAIL);
            return Status(grpc::ALREADY_EXISTS, logger_str);
          }
          // Add node to new and old cluster data structures
          m_cluster_info[cluster_name].node_names.push_back(node_name);
          m_cluster_map[cluster_name][curr_node.node_ip] = curr_node.node_port;
          // Update internal node_info
          curr_node.cluster_name = cluster_name;
          logger_str = "Node " + node_name + " added to cluster " +
                       m_registered_nodes[node_name].cluster_name;
          svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::DEBUG,
                     logger_str.c_str());
        } else {
          // Remove node from cluster
          std::vector<std::string> &node_names =
              m_cluster_info[cluster_name].node_names;
          auto it = std::find(node_names.begin(), node_names.end(), node_name);
          if (it != node_names.end()) {
            node_names.erase(it);
          } else {
            logger_str = "Node " + node_name + " not found in cluster " +
                         cluster_name + ", could not remove it from cluster.";
            svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                       logger_str.c_str());
            resp->set_error_id_or_string_if_any(logger_str);
            resp->set_error_code(SVK_STATUS_FAIL);
            return Status(grpc::NOT_FOUND, logger_str);
          }
          // Remove node from old cluster data structure
          if (!m_cluster_map[cluster_name].erase(curr_node.node_ip)) {
            logger_str = "Node " + node_name + " not found in cluster " +
                         cluster_name + ", in old cluster map.";
            svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                       logger_str.c_str());
            resp->set_error_id_or_string_if_any(logger_str);
            resp->set_error_code(SVK_STATUS_FAIL);
            return Status(grpc::NOT_FOUND, logger_str);
          }
          // Update internal node_info
          curr_node.cluster_name = "";
          logger_str = "Node " + node_name + " removed from cluster " +
                       cluster_name + ", cluster now contains " +
                       std::to_string(m_cluster_map[cluster_name].size()) +
                       " nodes.";
          svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::DEBUG,
                     logger_str.c_str());
        }

      } else {
        logger_str =
            "Invalid cluster or node, could not add/remove node from cluster.";
        svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                   logger_str.c_str());
        resp->set_error_id_or_string_if_any(logger_str);
        resp->set_error_code(SVK_STATUS_FAIL);
        return Status(grpc::INVALID_ARGUMENT, logger_str);
      }
    }
    logger_str =
        "Nodes successfully added/removed from cluster " + cluster_name;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    // Generate json response
    json cluster_json = json::array();
    json nodes_in_cluster = ClusterResponseJson(cluster_name);
    cluster_json.push_back(nodes_in_cluster);
    json response;
    response["clusters"] = cluster_json;
    resp->set_command_response(response.dump());

    return Status::OK;
  } catch (json::exception &e) {
    std::string exception_str = e.what();
    logger_str = "JSON error: " + exception_str;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any("Error parsing json command_params");
    resp->set_error_code(SVK_STATUS_FAIL);
    return Status(grpc::INVALID_ARGUMENT, "Error parsing json command_params");
  }
}

Status ControllerServicer::ClusterAPI(ServerContext *ctxt,
                                      const svk::ClusterRequest *req,
                                      svk::ClusterResponse *resp) {
  Status status;
  std::string cluster_name = req->cluster_name();
  std::string command_name = req->command_name();
  std::string command_params = req->command_params();
  std::string logger_str;

  resp->set_api_version(API_VERSION);

  logger_str = command_name + " called";

  if (command_name == "create_cluster") {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    status = CreateCluster(cluster_name, command_params, resp);
  } else if (command_name == "delete_cluster") {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    status = DeleteCluster(cluster_name, resp);
  } else if (command_name == "list_clusters") {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    status = ListClusters(resp);
  } else if (command_name == "list_nodes_in_cluster") {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    status = ListNodesInCluster(cluster_name, resp);
  } else if (command_name == "add_node_to_cluster" ||
             command_name == "remove_node_from_cluster") {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    status = AddRemoveNode(cluster_name, command_name, command_params, resp);
  } else {
    logger_str = "ClusterAPI received invalid command name " + command_name;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any(
        "ClusterAPI received invalid command name");
    resp->set_error_code(SVK_STATUS_FAIL);
    status = Status(grpc::INVALID_ARGUMENT,
                    "ClusterAPI received invalid command name");
  }
  return status;
}

Status ControllerServicer::ListNodes(svk::NodeResponse *resp) {
  std::string logger_str;
  Status status;

  //  Creating json in the following format:
  // {
  //     "node_info":[
  //       {
  //           "node_name":"cognos_node1",
  //           "node_port":"9998",
  //           "node_ip": "<IP addr>",
  //           "node_type": <controller/host>,
  //           "status": "online/offline"
  //       },
  //    ]
  // }
  using json = nlohmann::json;
  json node_info;
  json node_array = json::array();
  for (auto &curr_node : m_registered_nodes) {
    json curr_node_info;
    curr_node_info["node_name"] = curr_node.second.node_name;
    curr_node_info["node_port"] = curr_node.second.node_port;
    curr_node_info["node_ip"] = curr_node.second.node_ip;
    curr_node_info["status"] = node_status_to_str.at(curr_node.second.status);
    node_array.push_back(curr_node_info);
  }
  node_info["node_info"] = node_array;

  resp->set_error_code(0);
  resp->set_command_response(node_info.dump());
  logger_str = "list_nodes called successfully, found " +
               std::to_string(m_registered_nodes.size()) + " nodes";
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  return Status::OK;
}

Status ControllerServicer::NodeAPI(ServerContext *ctxt,
                                   const svk::NodeRequest *req,
                                   svk::NodeResponse *resp) {
  std::string logger_str;
  Status status;
  std::string cluster_name = req->cluster_name();
  std::string node_name = req->node_name();
  std::string feature_id = req->feature_id();
  std::string command_name = req->command_name();
  std::string command_params = req->command_params();

  resp->set_api_version(API_VERSION);

  if (command_name.length() == 0) {
    logger_str = "NodeAPI called with empty command_name";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any("Invalid node request parameters");
    resp->set_error_code(1);
    std::cout << "cmd name len" << std::endl;
    return Status(grpc::INVALID_ARGUMENT, "Invalid node request parameters");
  }

  if (command_name == "list_nodes") {
    status = ListNodes(resp);
  } else {
    logger_str = "Invalid command name " + command_name;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    resp->set_error_id_or_string_if_any("Invalid node command name");
    resp->set_error_code(1);
    std::cout << resp->error_code() << std::endl;
    status = Status(grpc::INVALID_ARGUMENT, "Invalid node command name");
  }

  return status;
}

std::shared_ptr<Server> InitializeServicer(ControllerServicer *svcr) {
  std::string logger_str;

  if (svcr == nullptr || svcr->get_svk_config_controller_id().length() == 0 ||
      svcr->get_svk_config_controller_port().length() == 0) {
    svk_logger(
        CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
        "Invalid servicer object or the node_id and the port are invalid");
    return nullptr;
  }
  std::string server_address = svcr->get_svk_config_controller_id() + ":" +
                               svcr->get_svk_config_controller_port();

  logger_str = "Server listening on " + server_address;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  grpc::EnableDefaultHealthCheckService(true);
  grpc::reflection::InitProtoReflectionServerBuilderPlugin();
  ServerBuilder builder;
  int selected_port;

  // Listen on the given address without any authentication mechanism.
  builder.AddListeningPort(server_address, grpc::InsecureServerCredentials(),
                           &selected_port);

  // Register "service" as the instance through which we'll communicate with
  // clients. In this case it corresponds to an *synchronous* service.
  // builder.RegisterService(new Servicer(svk_conf_file, framework_lib_path));
  builder.RegisterService(svcr);
  // Finally assemble the server.
  std::shared_ptr<Server> server(builder.BuildAndStart());
  if (server == nullptr) {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               "Controller Server failed to start");
    return nullptr;
  }

  svcr->set_server(server);

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "Controller Server instance successfully created");
  // Wait for the server to shutdown. Note that some other thread must be
  // responsible for shutting down the server for this call to ever return.
  return server;
}

void signal_handler(int signal) {
  std::string logger_str;
  logger_str = "Received signal " + std::to_string(signal);
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::WARN, logger_str.c_str());

  gSignalStatus.store(signal);
}

#define SUBSCRIBER_PORT "5555"
int StartSLAThreadForTiering(ControllerServicer *svcr) {
  // A map of <node_name> with the socket
  std::unordered_map<std::string, void *> socket_map;
  std::string logger_str;
  zmq::pollitem_t *items;
  svk_slat_logic_output data;
  std::string topic = "APP_SLA_DEGRADED";
  std::unordered_map<std::string, std::unordered_map<std::string, std::string>>
      m_cluster_map;
  std::string node_name;
  std::string cluster_name;
  int status = -1;
  int socket_map_count = 0;
  // TODO: Workaround to call TM module only once
  bool tm_flag = false;

  while (true) {
    if (svcr->get_stop_flag() == true) {
      logger_str = "Detected the stop flag enabled";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
      break;
    }
    if (svcr->is_config_changed() == true) {
      svcr->set_config_changed(false);
      logger_str = "Detected the cluster config change";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
      m_cluster_map = svcr->get_cluster_map();
      for (auto itr = m_cluster_map.begin(); itr != m_cluster_map.end();
           ++itr) {
        cluster_name = itr->first;
        for (auto nodes = itr->second.begin(); nodes != itr->second.end();
             ++nodes) {
          node_name = nodes->first;
          if (socket_map[node_name] == nullptr) {
            void *zmq_context;
            void *zmq_socket;
            status =
                initialize_sub(&zmq_context, &zmq_socket, node_name.c_str(),
                               SUBSCRIBER_PORT, topic.c_str());
            if (status != 0) {
              logger_str =
                  "Error in initializing the subscriber for node " + node_name;
              svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                         logger_str.c_str());
            } else {
              logger_str = "Initialized the subscriber for node " + node_name;
              svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                         logger_str.c_str());
              socket_map[node_name] = zmq_socket;
            }
          }
        }
      }
      socket_map_count = socket_map.size();
      if (socket_map_count) {
        items = new zmq::pollitem_t[socket_map_count];
        int count = 0;
        for (auto itr = socket_map.begin(); itr != socket_map.end(); ++itr) {
          *(items + count) = {itr->second, 0, ZMQ_POLLIN, 0};
          count++;
        }
      }
    }

    if (socket_map_count) {
      try {
        int rc =
            zmq::poll(items, socket_map_count, std::chrono::milliseconds(1000));
        if (rc > 0) {
          for (int i = 0; i < socket_map_count; i++) {
            if (items[i].revents && ZMQ_POLLIN) {
              status = get_data(&items[i].socket, &data);
              if (status != ((int)topic.length() + (int)sizeof(data))) {
                // error
                logger_str =
                    "Error in receiving the data for node " + node_name;
                svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                           logger_str.c_str());

              } else {
                // TODO: Workaround to call TM module only once
                if (tm_flag) {
                  continue;
                }
                tm_flag = true;

                logger_str =
                    "Device's numa " + std::string(data.device_name) +
                    " on host " + std::string(data.host_name) +
                    " for the app " + std::string(data.app_name) +
                    " deviated than expected - Reported latency_ns = " +
                    std::to_string(data.avgLatencyns);
                svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::WARN,
                           logger_str.c_str());

                // Received the event for SLA deviation. Send a command to TM
                // module with the params expected at this point of time.
                node_name = "";
                for (auto itr = m_cluster_map.begin();
                     itr != m_cluster_map.end(); ++itr) {
                  cluster_name = itr->first;
                  for (auto nodes = itr->second.begin();
                       nodes != itr->second.end(); ++nodes) {
                    if (nodes->first == data.host_name) {
                      node_name = data.host_name;
                      break;
                    }
                  }
                }
                if (node_name.length() != 0) {
                  svk::CommandRequest req;
                  svk::CommandResponse resp;
                  req.set_cluster_id(cluster_name);
                  req.set_node_id(node_name);
                  req.set_feature_id(feature_id::CXL);
                  std::string feature_params =
                      "cluster_id=" + cluster_name +
                      ";command=StartTuning;application="
                      "gemfire;application_id=" +
                      std::to_string(getpid()) +
                      ";dram_node=0;cxl_node=1;"
                      "sla_iops=150000;sla_size=1024;sla_latencyus=750";
                  req.set_feature_params(feature_params);
                  Client client(svcr->get_svk_config_controller_id(),
                                svcr->get_svk_config_controller_port());
                  Status client_grpc_status =
                      client.ProcessControllerCommand(&req, &resp);
                  if (client_grpc_status.ok()) {
                    logger_str =
                        "Command to the TM module with feature_params " +
                        feature_params + "is successful";
                    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                               logger_str.c_str());
                  } else {
                    logger_str = "Command with feature_params " +
                                 feature_params + "is failed";
                    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                               logger_str.c_str());
                  }
                }
              }
            }
          }
        }
      } catch (zmq::error_t &e) {
        std::string errorMessage = e.what();
        logger_str =
            "Exception in starting the subscriber poller" + errorMessage;
        svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                   logger_str.c_str());
        return -1;
      }
    } else {
      // sleep for 2 seconds if no nodes are registered with the controller
      sleep(2);
    }
  }
  return 0;
}

int StopSLAThreadForTiering(ControllerServicer *svcr) {
  svcr->set_stop_flag();
  return 0;
}

int StartServer(std::string svk_conf_file, bool blocking) {
  int status = -1;
  std::thread *sla_thread;
  std::signal(SIGTERM, signal_handler);
  std::signal(SIGSEGV, signal_handler);
  std::signal(SIGINT, signal_handler);
  std::signal(SIGABRT, signal_handler);

  ControllerServicer *svcr(new ControllerServicer(svk_conf_file));
  if (svcr->get_state() == false) {
    std::cout << "Servicer is not initialized properly. Exiting" << std::endl;
    return status;
  }
  auto server = InitializeServicer(svcr);
  if (server != nullptr) {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               "Starting the controller server to process the commands");
    if (blocking == true) {
      sla_thread = new std::thread(&StartSLAThreadForTiering, svcr);
      if (sla_thread == nullptr) {
        svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                   "Failed in starting the thread SLAThreadForTiering");
        delete svcr;
        return status;
      }

      while (gSignalStatus.load() == -1) sleep(5);
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 "The controller server is stopped gracefully");
      StopSLAThreadForTiering(svcr);
      sla_thread->join();
      delete svcr;
    }
    status = 0;
  } else {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               "Error in starting the server instance");
  }
  return status;
}

#ifndef BUILD_TESTING
int main(int argc, char **argv) {
  int status = -1;
  absl::ParseCommandLine(argc, argv);
  std::string svk_conf_file = absl::GetFlag(FLAGS_svk_conf_file);

  status = StartServer(svk_conf_file, true);
  return status;
}
#endif
