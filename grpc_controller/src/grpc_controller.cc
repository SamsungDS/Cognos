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

Status ControllerServicer::RegisterNode(ServerContext *ctxt,
                                        const svk::RegisterRequest *req,
                                        svk::RegisterResponse *resp) {
  std::string cluster_id = req->cluster_id();
  std::string node_id = req->node_id();
  std::string node_port = req->node_port();
  std::string node_info = node_id + ":" + node_port;
  std::string logger_str;
  int status = -1;
  int device_info_status;

  logger_str = "RegisterNode called with cluster_id:" + cluster_id +
               " node_id:" + node_id;
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  if (cluster_id.length() == 0 || node_id.length() == 0 ||
      node_port.length() == 0) {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               "Invalid input. One of the arguments is zero length");
    resp->set_status(
        "One of the input parameters (cluster_id/node_id/node_port) is of zero "
        "length");
    resp->set_error_code(status);
    return Status(grpc::INVALID_ARGUMENT,
                  "Invalid input - zero length arg given");
  }

  if (m_cluster_map.find(cluster_id) == m_cluster_map.end()) {
    logger_str = "Registering the cluster_id: " + cluster_id;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
    m_cluster_map[cluster_id][node_id] = node_port;
    logger_str =
        "Registered the node_id " + node_info + " with cluster:" + cluster_id;
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());
  } else {
    logger_str = "Found the cluster_id: " + cluster_id + " already registered";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
               logger_str.c_str());

    if (m_cluster_map[req->cluster_id()].find(node_id) ==
        m_cluster_map[req->cluster_id()].end()) {
      m_cluster_map[cluster_id][node_id] = node_port;
      logger_str =
          "Registered the node_id " + node_info + " with cluster:" + cluster_id;
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
    } else {
      logger_str = "Node with node_id " + node_info + " already registered";
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 logger_str.c_str());
    }
  }

  device_info_status = g_sla_device_hlpr->GetDeviceInfo(node_id, node_port);
  if (device_info_status != 0) {
    return Status(grpc::UNKNOWN, "Failed to get devices");
  }
  m_config_changed = true;
  status = 0;
  resp->set_status("Success");
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
