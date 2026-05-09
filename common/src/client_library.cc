#include "client_library.h"

#include <thread>

std::chrono::system_clock::time_point get_time_in_seconds(uint32_t timeout) {
  return std::chrono::system_clock::now() + std::chrono::seconds(timeout);
}

static void configureClientContext(ClientContext& ctxt) {
  // Set a deadline of 180 seconds maximum to process the command or exit with
  // deadline exceeded error
  ctxt.set_deadline(get_time_in_seconds(GRPC_COMMAND_DEADLINE_TIMEOUT));
  return;
}

Client::Client(const std::string& node, const std::string& port) {
  std::string node_and_port = node + ":" + port;
  // Create channel args with keepalive and reconnection settings for the grpc
  // channel
  grpc::ChannelArguments channel_args;
  channel_args.SetInt(GRPC_ARG_KEEPALIVE_TIME_MS, 30000);
  channel_args.SetInt(GRPC_ARG_KEEPALIVE_TIMEOUT_MS, 10000);
  channel_args.SetInt(GRPC_ARG_KEEPALIVE_PERMIT_WITHOUT_CALLS, 1);
  channel_args.SetInt(GRPC_ARG_HTTP2_MAX_PINGS_WITHOUT_DATA, 0);
  // The grpc reconnection implements an exponential backoff algorithm to
  // prevent overwhelming servers and can be maxed to 120 sec. Reduce the
  // maximum to 30s so that the client doesnt take too much time to reconnect
  // in case of heartbeat manager to detect when the service is up
  channel_args.SetInt(GRPC_ARG_MIN_RECONNECT_BACKOFF_MS, 1000);
  channel_args.SetInt(GRPC_ARG_MAX_RECONNECT_BACKOFF_MS,
                      30000);  // 30 seconds max
  channel_args.SetInt(GRPC_ARG_INITIAL_RECONNECT_BACKOFF_MS, 1000);

  channel_ = grpc::CreateCustomChannel(
      node_and_port, grpc::InsecureChannelCredentials(), channel_args);
  fwk_stub_ = CommandFwk::NewStub(channel_);
  ctrlr_stub_ = Controller::NewStub(channel_);
  health_stub_ = Health::NewStub(channel_);
}

bool Client::CheckServerHealth(const std::string& service_name) {
  HealthCheckRequest request;
  // Set the service name to check the health of service
  request.set_service(service_name);

  HealthCheckResponse response;
  grpc::ClientContext context;
  // Setting a small deadline for the health check
  context.set_deadline(std::chrono::system_clock::now() +
                       std::chrono::seconds(10));

  grpc::Status status = health_stub_->Check(&context, request, &response);

  if (status.ok()) {
    return response.status() == HealthCheckResponse::SERVING;
  }

  return false;
}

Status Client::ProcessNodeCommand(const svk::CommandRequest* req,
                                  svk::CommandResponse* resp) {
  ClientContext ctxt;
  configureClientContext(ctxt);
  Status status = fwk_stub_->ProcessNodeCommand(&ctxt, *req, resp);
  return status;
}

Status Client::ProcessControllerCommand(const svk::CommandRequest* req,
                                        svk::CommandResponse* resp) {
  ClientContext ctxt;
  configureClientContext(ctxt);
  Status status = ctrlr_stub_->ProcessControllerCommand(&ctxt, *req, resp);
  return status;
}

Status Client::ListClusterNodes(const svk::ListClusterCommandRequest* req,
                                svk::ListClusterCommandResponse* resp) {
  ClientContext ctxt;
  configureClientContext(ctxt);
  Status status = ctrlr_stub_->ListClusterNodes(&ctxt, *req, resp);
  return status;
}

Status Client::RegisterNode(const svk::RegisterRequest* req,
                            svk::RegisterResponse* resp) {
  ClientContext ctxt;
  // Register node should wait till the controller is ready to connect to.
  // Not setting the deadline as we don't want the node to timeout before
  // registration.
  ctxt.set_wait_for_ready(true);
  Status status = ctrlr_stub_->RegisterNode(&ctxt, *req, resp);

  return status;
}

Status Client::UnregisterNode(const svk::UnregisterRequest* req,
                              svk::UnregisterResponse* resp) {
  ClientContext ctxt;
  configureClientContext(ctxt);
  Status status = ctrlr_stub_->UnregisterNode(&ctxt, *req, resp);
  return status;
}

Status Client::SetNodeStatus(const svk::SetNodeStatusRequest* req,
                             svk::SetNodeStatusResponse* resp) {
  ClientContext ctxt;
  configureClientContext(ctxt);
  Status status = ctrlr_stub_->SetNodeStatus(&ctxt, *req, resp);
  return status;
}

Status Client::ClusterAPI(const svk::ClusterRequest* req,
                          svk::ClusterResponse* resp) {
  ClientContext ctxt;
  configureClientContext(ctxt);
  Status status = ctrlr_stub_->ClusterAPI(&ctxt, *req, resp);
  return status;
}

Status Client::NodeAPI(const svk::NodeRequest* req, svk::NodeResponse* resp) {
  ClientContext ctxt;
  configureClientContext(ctxt);
  Status status = ctrlr_stub_->NodeAPI(&ctxt, *req, resp);
  return status;
}

Status Client::FeatureAPI(const svk::FeatureRequest* req,
                          svk::FeatureResponse* resp) {
  ClientContext ctxt;
  configureClientContext(ctxt);

  Status status = ctrlr_stub_->FeatureAPI(&ctxt, *req, resp);
  return status;
}

Status Client::EventAPI(const svk::EventRequest* req,
                        svk::EventResponse* resp) {
  ClientContext ctxt;
  configureClientContext(ctxt);
  Status status = ctrlr_stub_->EventAPI(&ctxt, *req, resp);
  return status;
}

Status Client::SLAManagementAPI(const svk::SLAManagementRequest* req,
                                svk::SLAManagementResponse* resp) {
  ClientContext ctxt;
  configureClientContext(ctxt);
  Status status = ctrlr_stub_->SLAManagementAPI(&ctxt, *req, resp);
  return status;
}

Status Client::StatsAPI(const svk::StatsRequest* req,
                        svk::StatsResponse* resp) {
  ClientContext ctxt;
  configureClientContext(ctxt);
  Status status = ctrlr_stub_->StatsAPI(&ctxt, *req, resp);
  return status;
}

Status Client::ProcessNodeConfiguration(const svk::NodeConfigRequest* req,
                                        svk::NodeConfigResponse* resp) {
  ClientContext ctxt;
  configureClientContext(ctxt);
  Status status = fwk_stub_->ProcessNodeConfiguration(&ctxt, *req, resp);
  return status;
}

int Client::GetChannelState(grpc_connectivity_state& state) {
  if (channel_) {
    state = channel_->GetState(true);
    return 0;
  }
  return -1;
}

// Wait till the client's grpc channel state is READY
// Across the node service restarts, the grpc channel may be in transient or
// other non-ready states. Since we are using the grpc channel to get some
// information related to CXL devices or node details, the call failure may
// result in the data getting missed
int Client::WaitForConnected() {
  std::string logger_str;
  int status = -1;
  grpc_connectivity_state ch_state;
  int ch_status;

  while (true) {
    ch_status = GetChannelState(ch_state);
    if (ch_status == -1) {
      logger_str = "Channel status for node is not initialized";
      std::cerr << logger_str << std::endl;
    } else if (ch_state != grpc_connectivity_state::GRPC_CHANNEL_READY) {
      logger_str = "Channel status for node is " + std::to_string(ch_state);
      std::cout << logger_str << std::endl;
    } else if (ch_state == grpc_connectivity_state::GRPC_CHANNEL_READY) {
      logger_str = "Channel status for node is ready";
      std::cout << logger_str << std::endl;

      status = 0;
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(2000));
  }
  return status;
}
