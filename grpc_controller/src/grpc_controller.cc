#include "grpc_controller.h"

#include <csignal>
#include <set>

#include "client_library.h"
#define MAX_SIZE 4096

#ifndef BUILD_TESTING
ABSL_FLAG(std::string, svk_conf_file, "", "svk configuration file to read");
#endif

using namespace svk;

std::atomic<int> gSignalStatus = -1;

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
  resp->set_status("Success");
  resp->set_error_code(status);

  return Status::OK;
}

Status ControllerServicer::ProcessControllerCommand(
    ServerContext *ctxt, const svk::CommandRequest *req,
    svk::CommandResponse *resp) {
  Status status;
  svk::CommandRequest req_node;
  svk::CommandResponse resp_node;

  if (req->cluster_id().length() == 0 || req->feature_params().length() == 0) {
    std::string logger_str;
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
    std::string logger_str;
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
        std::string logger_str;
        logger_str = "ProcessControllerCommand called for node_id " + *itr +
                     "is not part of cluster_id " + req->cluster_id();
        svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
                   logger_str.c_str());
        return Status(grpc::INVALID_ARGUMENT, "node_id not part of cluster");
      }
    }
  }

  for (auto itr = m_cluster_map[req->cluster_id()].begin();
       itr != m_cluster_map[req->cluster_id()].end(); ++itr) {
    if (count && nodes.find(itr->first) == nodes.end()) continue;
    req_node.set_node_id(itr->first);
    req_node.set_feature_id(req->feature_id());
    req_node.set_feature_params(req->feature_params());
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

int StartServer(std::string svk_conf_file, bool blocking) {
  int status = -1;
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
      while (gSignalStatus.load() == -1) sleep(5);
      svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
                 "The controller server is stopped gracefully");
      delete svcr;
    }
  } else {
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               "Error in starting the server instance");
  }
  status = 0;
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
