#include "grpc_server.h"

#include <csignal>
#include <set>

#include "client_library.h"
#define MAX_SIZE 4096

#ifndef BUILD_TESTING
ABSL_FLAG(std::string, svk_conf_file, "", "svk configuration file to read");
#endif

using namespace std;
using namespace svk;

std::atomic<int> gSignalNodeStatus = -1;

int initialize_logger(const node_config &config) {
  int status = -1;

  if (svk_logger_init(MGMT_FW_LOGGER_MODULE_NAME, config.log_filename.c_str(),
                      log_level_map.at(config.log_level), config.log_file_count,
                      config.log_file_size,
                      config.log_sink_type.c_str()) == 0) {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
               "Mgmt FW Node logger is initialized");
    status = 0;
  } else {
    std::cout << "Mgmt FW Node logger initialization failed" << std::endl;
  }
  return status;
}

int read_svk_conf_file(const std::string svk_conf_file, node_config *config) {
  int status = -1;
  namespace pt = boost::property_tree;

  try {
    pt::ptree root;
    pt::read_json(svk_conf_file, root);
    pt::ptree mgmt_config_pt = root.get_child("svk_mgmt_fw_node");

    config->framework_conf_file =
        mgmt_config_pt.get<std::string>("framework.conf_file");
    if (config->framework_conf_file.length() == 0) {
      throw std::invalid_argument("Invalid framework config file");
    }
    config->cluster_id = mgmt_config_pt.get("cluster.id", "");
    config->controller_id =
        mgmt_config_pt.get("controller.id", DEFAULT_CONTROLLER_ID);
    config->controller_port = mgmt_config_pt.get<std::string>(
        "controller.port", DEFAULT_CONTROLLER_PORT);
    config->node_name = mgmt_config_pt.get("node.name", "");
    config->node_id = mgmt_config_pt.get("node.id", DEFAULT_NODE_ID);
    if (config->node_name.length() == 0) {
      config->node_name = config->node_id;
    }
    config->node_port =
        mgmt_config_pt.get<std::string>("node.port", DEFAULT_NODE_PORT);

    try {
      pt::ptree logger_info_pt = root.get_child("svk_mgmt_fw_node.logger");
      config->log_level = logger_info_pt.get<std::string>(
          "log_level", MGMT_FW_LOGGER_DEFAULT_LEVEL);
      config->log_filename = logger_info_pt.get<std::string>(
          "log_file_name", MGMT_FW_NODE_DEFAULT_LOG_FILE);
      config->log_file_count = logger_info_pt.get<uint64_t>(
          "log_file_count", MGMT_FW_LOGGER_DEFAULT_FILE_COUNT);
      config->log_file_size = logger_info_pt.get<uint64_t>(
          "log_file_size", MGMT_FW_LOGGER_DEFAULT_FILE_SIZE);
      config->log_sink_type = logger_info_pt.get<std::string>(
          "sink_type", MGMT_FW_LOGGER_DEFAULT_SINK_TYPE);
    } catch (std::exception &e) {
      cout
          << "Unable to read Logger section of Mgmt FW in SVK config. Error -> "
          << e.what() << endl;
      // Use defaults
      config->log_level = "INFO";
      config->log_filename = MGMT_FW_NODE_DEFAULT_LOG_FILE;
      config->log_file_count = MGMT_FW_LOGGER_DEFAULT_FILE_COUNT;
      config->log_file_size = MGMT_FW_LOGGER_DEFAULT_FILE_SIZE;
      config->log_sink_type = "rotating_file";
    }
    status = 0;
  } catch (std::exception &e) {
    cerr << "Unable to read SVK config. Error -> " << e.what() << endl;
  }

  return status;
}

Servicer::Servicer(const std::string &svk_conf_file) {
  struct stat buf;
  int ret_val = -1;
  node_config config;
  std::string logger_str;

  if (stat(svk_conf_file.c_str(), &buf) != 0) {
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

  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "Initializing the svk framework");

  m_svk_config = config;

  ret_val = initialize_svk(config.framework_conf_file.c_str(), nullptr);
  if (ret_val) {
    logger_str = "initialize_svk failed with error " + std::to_string(ret_val);
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR, logger_str.c_str());
    m_initialized_flag = false;
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
               "Closing the logger instance");
    svk_logger_close(MGMT_FW_LOGGER_MODULE_NAME);
  } else {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
               "initialize_svk called successfully");
    m_initialized_flag = true;
  }
}

Servicer::~Servicer() {
  auto server = this->get_server();

  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "Shutting down the gRPC Node server");
  if (server) server->Shutdown();
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "gRPC Node server is shutdown");
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "Closing the logger instance as part of shutdown");

  svk_logger_close(MGMT_FW_LOGGER_MODULE_NAME);
  return;
}

Status Servicer::ProcessNodeCommand(ServerContext *ctxt,
                                    const svk::CommandRequest *req,
                                    svk::CommandResponse *resp) {
  svk_pass_thru_cmd svk_cmd;
  svk_input svk_input;
  svk_output svk_output;
  std::string output_str;
  int ret;
  Status status;
  std::string feature_params = req->feature_params();
  std::string logger_str;
  char buffer[MAX_SIZE];

  svk_cmd.feat_id = (feature_id)req->feature_id();
  svk_input.input_buffer = (uint8_t *)&feature_params[0];
  svk_input.len = feature_params.length();
  svk_output.output_buffer = (uint8_t *)&buffer[0];
  svk_output.len = MAX_SIZE;

  ret = execute_svk_feature_sync(&svk_cmd, &svk_input, &svk_output);
  if (svk_output.status == 0 && ret == 0) {
    status = Status::OK;
  } else {
    status = Status(grpc::UNKNOWN, "Failed to run command");
    logger_str = "Failed to run command for node_id " + req->node_id() +
                 " feature_id " + std::to_string(svk_cmd.feat_id) +
                 " params [" + feature_params + "]";
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR, logger_str.c_str());
    return status;
  }

  if (svk_output.len) {
    CommandResponse_NodeResponse *response = resp->add_node_responses();
    output_str.assign((char *)svk_output.output_buffer, svk_output.len);
    response->set_output(output_str);
    response->set_node_id(req->node_id());
  }
  return status;
}

int RegisterNodeWithController(const node_config &config) {
  int status = -1;
  Status grpc_status;
  std::string logger_str;

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_node_name(config.node_name);
  req->set_node_ip(config.node_id);
  req->set_node_port(config.node_port);
  req->set_cluster_name(config.cluster_id);

  Client client(config.controller_id, config.controller_port);

  logger_str = "Registering with the Controller " + config.controller_id +
               " at port " + config.controller_port;
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  grpc_status = client.RegisterNode(req, resp);
  if (grpc_status.ok() != true) {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
               "Failed to register with the controller");
    return status;
  }

  status = 0;
  return status;
}

std::shared_ptr<Server> InitializeNodeServicer(Servicer *svcr) {
  std::string logger_str;
  int status = -1;
  node_config config;

  if (svcr == nullptr || svcr->get_state() == false) {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
               "Invalid servicer object or object is not fully initialized");
    return nullptr;
  }
  config = svcr->get_svk_config();
  if (config.node_id.length() == 0 || config.node_port.length() == 0 ||
      config.node_name.length() == 0) {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
               "Invalid node_name, node_id, or node_port");
    return nullptr;
  }
  std::string server_address = config.node_id + ":" + config.node_port;

  logger_str = "Server listening on " + server_address;
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

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
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
               "Server failed to start");
    return nullptr;
  }
  svcr->set_server(server);

  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "Server instance successfully created");

  if (config.controller_id.length()) {
    status = RegisterNodeWithController(config);
    if (status) {
      svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
                 "Node Server failed to register with the controller");
      // Call destructor
      return nullptr;
    }
  }

  return server;
}

void signal_node_handler(int signal) {
  std::string logger_str;
  logger_str = "Received signal " + std::to_string(signal);
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::WARN, logger_str.c_str());

  gSignalNodeStatus.store(signal);
}

int StartNodeServer(std::string svk_conf_file, bool blocking) {
  int status = -1;

  Servicer *svcr(new Servicer(svk_conf_file));
  if (svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return status;
  }
  auto server = InitializeNodeServicer(svcr);
  if (server != nullptr) {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
               "Starting the node server to process the commands");

    std::signal(SIGTERM, signal_node_handler);
    std::signal(SIGSEGV, signal_node_handler);
    std::signal(SIGINT, signal_node_handler);
    std::signal(SIGABRT, signal_node_handler);

    if (blocking == true) {
      while (gSignalNodeStatus.load() == -1) sleep(5);
      svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
                 "The node server is stopped gracefully");
      delete svcr;
    } else {
      svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
                 "The node server is started in non-blocking mode for UT");
    }
    status = 0;
  } else {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
               "Error in starting the node server instance");
  }
  return status;
}

#ifndef BUILD_TESTING
int main(int argc, char **argv) {
  int status = -1;

  absl::ParseCommandLine(argc, argv);
  std::string svk_conf_file = absl::GetFlag(FLAGS_svk_conf_file);
  status = StartNodeServer(svk_conf_file, true);
  return status;
}
#endif
