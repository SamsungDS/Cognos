#include "grpc_server.h"
#define MAX_SIZE 4096

ABSL_FLAG(std::string, svk_conf_file, "", "svk configuration file to read");

using namespace std;
using namespace svk;

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
    config->cluster_id = mgmt_config_pt.get("cluster.id", DEFAULT_CLUSTER_ID);
    config->controller_id =
        mgmt_config_pt.get("controller.id", DEFAULT_CONTROLLER_ID);
    config->controller_port = mgmt_config_pt.get<std::string>(
        "controller.port", DEFAULT_CONTROLLER_PORT);
    config->node_id = mgmt_config_pt.get("node.id", DEFAULT_NODE_ID);
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

  m_svk_config = config;
  m_initialized_flag = true;

  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "Initializing the svk framework");

  ret_val = initialize_svk(config.framework_conf_file.c_str(), nullptr);
  if (ret_val) {
    logger_str = "initialize_svk failed with error " + std::to_string(ret_val);
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR, logger_str.c_str());
  } else {
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
               "initialize_svk called successfully");
  }
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

  output_str.resize(MAX_SIZE, 0);
  svk_cmd.feat_id = (feature_id)req->feature_id();
  svk_input.input_buffer = (uint8_t *)feature_params.c_str();
  svk_input.len = feature_params.length();
  svk_output.output_buffer = (uint8_t *)output_str.data();
  svk_output.len = MAX_SIZE;

  ret = execute_svk_feature_sync(&svk_cmd, &svk_input, &svk_output);
  if (svk_output.status == 0 && ret == 0) {
    status = Status::OK;
  } else {
    status = Status(grpc::UNKNOWN, "Failed to run command");
    logger_str = "Failed to run command for node_id " + req->node_id() +
                 " feature_id " + std::to_string(svk_cmd.feat_id) + " params " +
                 feature_params;
    svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR, logger_str.c_str());
  }

  if (svk_output.len) {
    output_str.resize(svk_output.len);
    CommandResponse_NodeResponse *response = resp->add_node_responses();
    response->set_output(output_str);
    response->set_node_id(req->node_id());
  }
  return status;
}

std::shared_ptr<Server> Init(Servicer *svcr) {
  std::string logger_str;

  if (svcr == nullptr || svcr->get_svk_config_node_id().length() == 0 ||
      svcr->get_svk_config_node_port().length() == 0) {
    svk_logger(
        MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
        "Invalid servicer object or the node_id and the port are invalid");
    return nullptr;
  }
  std::string server_address =
      svcr->get_svk_config_node_id() + ":" + svcr->get_svk_config_node_port();

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

  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "Server instance successfully created");
  // Wait for the server to shutdown. Note that some other thread must be
  // responsible for shutting down the server for this call to ever return.
  return server;
}

int main(int argc, char **argv) {
  absl::ParseCommandLine(argc, argv);
  Servicer *svcr(new Servicer(absl::GetFlag(FLAGS_svk_conf_file)));
  auto server = Init(svcr);

  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "Starting the server to process the commands");
  server->Wait();
  return 0;
}
