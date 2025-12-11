#include "client_library.h"

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
  channel =
      grpc::CreateChannel(node_and_port, grpc::InsecureChannelCredentials());
  fwk_stub_ = CommandFwk::NewStub(channel);
  ctrlr_stub_ = Controller::NewStub(channel);
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
