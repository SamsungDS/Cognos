#include "grpc_server.h"

#include <systemd/sd-daemon.h>

#include <condition_variable>
#include <csignal>
#include <mutex>
#include <set>
#include <thread>

#include "client_library.h"
#include "grpc/health/v1/health.grpc.pb.h"
constexpr size_t MAX_SIZE = 4096;

#ifndef BUILD_TESTING
ABSL_FLAG(std::string, svk_conf_file, "", "svk configuration file to read");
#endif

using namespace std;
using namespace svk;

std::atomic<int> gSignalNodeStatus = -1;
std::mutex gNodeSrvMutex;
std::condition_variable gNodeSrvCondVar;

void systemd_notify(int ready, const char *status) {
  sd_notifyf(0, "READY=%d\nSTATUS=%s", ready, status);
  return;
}

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

int read_svk_conf_file(const std::string &svk_conf_file, node_config *config) {
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
  systemd_notify(0, "Loading Cognos feature modules ...");

  ret_val = initialize_svk(config.framework_conf_file.c_str(), nullptr);
  if (ret_val) {
    logger_str = "initialize_svk failed with error " + std::to_string(ret_val);
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR, logger_str.c_str());
    m_initialized_flag = false;
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
               "Closing the logger instance");
    svk_logger_flush(MGMT_FW_LOGGER_MODULE_NAME);
  } else {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
               "initialize_svk called successfully");
    ret_val = -1;
    if (config.node_name.length()) {
      ret_val =
          set_node_name(config.node_name.c_str(), config.node_name.length());
      logger_str =
          "Node name " + config.node_name + " is set in the core framework";
    } else if (config.node_id.length()) {
      ret_val = set_node_name(config.node_id.c_str(), config.node_id.length());
      logger_str =
          "Node name " + config.node_id + " is set in the core framework";
    }
    if (ret_val != 0) {
      svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
                 "Error in setting the node_name or the node_id in the core "
                 "framework");
      svk_logger_flush(MGMT_FW_LOGGER_MODULE_NAME);
      m_initialized_flag = false;
      return;
    }
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

    if (config.cluster_id.length()) {
      ret_val = set_cluster_name(config.cluster_id.c_str(),
                                 config.cluster_id.length());
    }
    if (ret_val == 0) {
      logger_str =
          "Cluster name " + config.cluster_id + " is set in the core framework";
      svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());
    }

    // Initialize heartbeat manager for monitoring controller health
    InitializeHeartbeatManager();

    m_initialized_flag = true;
  }
}

Servicer::~Servicer() {
  auto server = get_server();
  // Stop heartbeat manager before cleanup
  if (m_heartbeat_manager) {
    m_heartbeat_manager->Stop();
  }
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "Shutting down the gRPC Node server");
  if (server) server->Shutdown();
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "gRPC Node server is shutdown");
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "Closing the logger instance as part of shutdown");
  cleanup_svk(nullptr, nullptr);

  svk_logger_flush(MGMT_FW_LOGGER_MODULE_NAME);
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
  std::string params;
  std::string logger_str;
  char buffer[MAX_SIZE];
  if (req->feature_name().length() != 0) {
    // If using feature_name (string) for execute
    logger_str =
        "ProcessNodeCommand using feature_name: " + req->feature_name();
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::DEBUG, logger_str.c_str());
    svk_cmd.out_format = (void *)req->feature_name().c_str();
    svk_cmd.len = req->feature_name().size();

    using json = nlohmann::json;
    json command_params;
    json res;
    res["command_params"] = "";
    try {
      if (req->command_params().length()) {
        command_params = json::parse(req->command_params());
        res["command_params"] = command_params;
      }
      res["command_name"] = req->command_name();
    } catch (json::exception &e) {
      logger_str =
          "Json parsing error in ProcessNodeCommand: " + std::string(e.what());
      svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
                 logger_str.c_str());
      status = Status(grpc::INVALID_ARGUMENT, logger_str);
      return status;
    }

    params = res.dump();
    svk_input.input_buffer = (uint8_t *)&params[0];
    svk_input.len = params.length();
  } else if (req->feature_id() >= POWER_THROTTLE &&
             req->feature_id() <= SLA_TRACKER) {
    // If using feature_id for execute
    logger_str = "ProcessNodeCommand using feature_id: " +
                 std::to_string(req->feature_id());
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::DEBUG, logger_str.c_str());
    svk_cmd.feat_id = (feature_id)req->feature_id();
    svk_cmd.len = 0;
    params = req->feature_params();
    svk_input.input_buffer = (uint8_t *)&params[0];
    svk_input.len = params.length();
  } else {
    // Must give either feature_id or feature_name for execute, fail if neither
    // exist
    logger_str =
        "ProcessNodeCommand received invalid feature_id and feature_name";
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR, logger_str.c_str());
    return Status(grpc::INVALID_ARGUMENT, logger_str);
  }
  svk_output.output_buffer = (uint8_t *)&buffer[0];
  svk_output.len = MAX_SIZE;

  ret = execute_svk_feature_sync(&svk_cmd, &svk_input, &svk_output);
  if (svk_output.status == 0 && ret == 0) {
    status = Status::OK;
  } else {
    std::string error_str = "Failed to run command with error: " +
                            std::to_string(svk_output.status);
    status = Status(grpc::UNKNOWN, error_str);
    logger_str = "Failed to run command for node_id " + req->node_id() +
                 " feature_id " + std::to_string(svk_cmd.feat_id) +
                 " params [" + params + "] with error " +
                 std::to_string(svk_output.status);
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

  logger_str =
      "Waiting for the controller to accept the node registration request";
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());
  std::cout << logger_str << std::endl;

  grpc_status = client.RegisterNode(req, resp);
  if (grpc_status.ok() != true) {
    logger_str = "Failed to register with the controller";
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR, logger_str.c_str());
    std::cout << logger_str << std::endl;
    return status;
  } else {
    logger_str = "Successfully registered with the controller";
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());
    std::cout << logger_str << std::endl;
  }

  status = 0;
  return status;
}

int SetNodeStatus(const node_config &config, std::string node_status) {
  svk::SetNodeStatusRequest *req(new svk::SetNodeStatusRequest());
  svk::SetNodeStatusResponse *resp(new svk::SetNodeStatusResponse());
  req->set_node_status(node_status);
  req->set_node_name(config.node_name);

  Client client(config.controller_id, config.controller_port);
  std::string logger_str = "Setting node status to " + node_status;
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  Status grpc_status = client.SetNodeStatus(req, resp);
  if (!grpc_status.ok()) {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
               "Failed to set node status");
    return -1;
  }
  return 0;
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

  // Set the Keepalive settings
  builder.AddChannelArgument(GRPC_ARG_KEEPALIVE_TIME_MS, 20000);
  builder.AddChannelArgument(GRPC_ARG_KEEPALIVE_TIMEOUT_MS, 5000);
  builder.AddChannelArgument(GRPC_ARG_KEEPALIVE_PERMIT_WITHOUT_CALLS, 1);
  builder.AddChannelArgument(
      GRPC_ARG_HTTP2_MIN_RECV_PING_INTERVAL_WITHOUT_DATA_MS, 20000);
  builder.AddChannelArgument(GRPC_ARG_HTTP2_MAX_PINGS_WITHOUT_DATA, 0);
  builder.AddChannelArgument(GRPC_ARG_HTTP2_MAX_PING_STRIKES, 2);
  builder.AddChannelArgument(GRPC_ARG_MAX_MESSAGE_LENGTH, 1024 * 1024 * 8);

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
    systemd_notify(0, "Waiting for the controller to register the node ...");
    status = RegisterNodeWithController(config);
    if (status) {
      svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
                 "Node Server failed to register with the controller");
      // Call destructor
      return nullptr;
    }
  }

  if (auto *node_health_service = server->GetHealthCheckService();
      node_health_service != nullptr) {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
               "HealthCheck enabled for Node Server");
    node_health_service->SetServingStatus(NODE_SERVICE_HEALTHCHECK_TAG, true);
  } else {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::WARN,
               "HealthCheck not enabled for Node Server");
  }
  systemd_notify(1, "Service is running and healthy.");

  return server;
}

void signal_node_handler(int signal) {
  std::string logger_str;
  logger_str = "Received signal " + std::to_string(signal);
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::WARN, logger_str.c_str());

  gSignalNodeStatus.store(signal);

  // If the signal is SIGSEGV, SIGABRT, or other fatal signals,
  // it's generally not safe to continue execution.
  if (signal == SIGSEGV || signal == SIGABRT) {
    // Log the error and exit or abort
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::FATAL,
               "Fatal signal to Node Server received. Aborting the service");
    // Reset to signal default handler
    std::signal(signal, SIG_DFL);
  } else {
    // Re-register the signal handler
    std::signal(signal, signal_node_handler);
  }
  return;
}

int Servicer::StartMonitorControllerThread() const {
  std::string logger_str;
  node_config config;

  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "Starting the Controller monitoring thread");
  config = this->get_svk_config();

  if (config.controller_id.length() == 0) {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::WARN,
               "Controller is not configured");
    return -1;
  }

  // Use heartbeat manager to monitor controller health
  if (m_heartbeat_manager) {
    // Set up callback for controller health status changes
    m_heartbeat_manager->SetHealthCallback(
        [this, &config]([[maybe_unused]] const std::string &controller_id,
                        [[maybe_unused]] const std::string &controller_ip,
                        HeartbeatStatus old_status,
                        HeartbeatStatus new_status) {
          std::string logger_str;
          if (new_status == HeartbeatStatus::HEALTHY &&
              old_status != HeartbeatStatus::HEALTHY) {
            svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
                       "Controller is alive again. Registering with the "
                       "controller again");
            int reg_status = RegisterNodeWithController(config);
            if (reg_status) {
              svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
                         "Node Server failed to register with the controller "
                         "through heartbeat callback");
            } else {
              systemd_notify(1, "Service is running and healthy.");
            }
          } else if (new_status != HeartbeatStatus::HEALTHY) {
            svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::WARN,
                       "Lost connection to the controller");
            systemd_notify(
                0,
                "Lost connection to controller. Waiting for the controller to "
                "reconnect ...");
          }
        });

    // Add controller as a peer to monitor
    m_heartbeat_manager->AddPeer(config.controller_id, config.controller_id,
                                 config.controller_port,
                                 CONTROLLER_SERVICE_HEALTHCHECK_TAG);

    // Start heartbeat monitoring
    m_heartbeat_manager->Start();
  }

  while (this->get_stop_flag() == false) {
    std::unique_lock lock(gNodeSrvMutex);

    // Sleep for 10 seconds or until the stop flag is set to true
    gNodeSrvCondVar.wait_for(
        lock, std::chrono::seconds(HEALTH_CHECK_RECONNECT_INTERVAL),
        [this]() { return this->get_stop_flag(); });
  }

  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "Exiting the Controller monitoring thread");
  return 0;
}

void Servicer::InitializeHeartbeatManager() {
  std::string logger_str;

  try {
    HeartbeatConfig config;
    // Read heartbeat config from config file if available
    // For now, use defaults
    m_heartbeat_manager = std::make_unique<HeartbeatManager>(config);

    logger_str = "Heartbeat manager initialized for node";
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());
  } catch (const std::exception &e) {
    logger_str =
        "Failed to initialize heartbeat manager: " + std::string(e.what());
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR, logger_str.c_str());
  }
}

int StartNodeServer(const std::string &svk_conf_file, bool blocking) {
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
               "The node server is ready to process the commands");

    std::signal(SIGTERM, signal_node_handler);
    std::signal(SIGSEGV, signal_node_handler);
    std::signal(SIGINT, signal_node_handler);
    std::signal(SIGABRT, signal_node_handler);

    systemd_notify(1, "Service is running and healthy.");

    if (blocking == true) {
      auto monitor_thread =
          std::thread(&Servicer::StartMonitorControllerThread, svcr);

      while (gSignalNodeStatus.load() == -1) {
        sleep(5);
      }
      systemd_notify(1, "Stopping the service ...");
      svcr->set_stop_flag();
      gNodeSrvCondVar.notify_one();

      SetNodeStatus(svcr->get_svk_config(), "offline");
      gSignalNodeStatus = -1;
      monitor_thread.join();
      svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
                 "Updated the node status to offline");
    } else {
      svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
                 "The node server is started in non-blocking mode for UT");
    }
    status = 0;
  } else {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
               "Error in starting the node server instance");
  }
  if (svcr) {
    delete svcr;
  }
  systemd_notify(1, "Service is Stopped");
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "The node server is stopped gracefully");
  svk_logger_close(MGMT_FW_LOGGER_MODULE_NAME);

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
