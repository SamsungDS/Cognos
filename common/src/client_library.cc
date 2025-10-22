#include "client_library.h"

Client::Client(std::string node, std::string port) {
  std::string node_and_port = node + ":" + port;
  channel =
      grpc::CreateChannel(node_and_port, grpc::InsecureChannelCredentials());
  fwk_stub_ = CommandFwk::NewStub(channel);
  ctrlr_stub_ = Controller::NewStub(channel);
}

Status Client::ProcessNodeCommand(const svk::CommandRequest* req,
                                  svk::CommandResponse* resp) {
  ClientContext ctxt;
  Status status = fwk_stub_->ProcessNodeCommand(&ctxt, *req, resp);
  return status;
}

Status Client::ProcessControllerCommand(const svk::CommandRequest* req,
                                        svk::CommandResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->ProcessControllerCommand(&ctxt, *req, resp);
  return status;
}

Status Client::ListClusterNodes(const svk::ListClusterCommandRequest* req,
                                svk::ListClusterCommandResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->ListClusterNodes(&ctxt, *req, resp);
  return status;
}

Status Client::RegisterNode(const svk::RegisterRequest* req,
                            svk::RegisterResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->RegisterNode(&ctxt, *req, resp);
  return status;
}

Status Client::UnregisterNode(const svk::UnregisterRequest* req,
                              svk::UnregisterResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->UnregisterNode(&ctxt, *req, resp);
  return status;
}

Status Client::SetNodeStatus(const svk::SetNodeStatusRequest* req,
                             svk::SetNodeStatusResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->SetNodeStatus(&ctxt, *req, resp);
  return status;
}

Status Client::ClusterAPI(const svk::ClusterRequest* req,
                          svk::ClusterResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->ClusterAPI(&ctxt, *req, resp);
  return status;
}

Status Client::NodeAPI(const svk::NodeRequest* req, svk::NodeResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->NodeAPI(&ctxt, *req, resp);
  return status;
}

Status Client::FeatureAPI(const svk::FeatureRequest* req,
                          svk::FeatureResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->FeatureAPI(&ctxt, *req, resp);
  return status;
}

Status Client::EventAPI(const svk::EventRequest* req,
                        svk::EventResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->EventAPI(&ctxt, *req, resp);
  return status;
}

Status Client::SLAManagementAPI(const svk::SLAManagementRequest* req,
                                svk::SLAManagementResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->SLAManagementAPI(&ctxt, *req, resp);
  return status;
}