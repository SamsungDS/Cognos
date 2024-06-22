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
  if (!status.ok()) {
    return status;
  }
  return status;
}

Status Client::ProcessControllerCommand(const svk::CommandRequest* req,
                                        svk::CommandResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->ProcessControllerCommand(&ctxt, *req, resp);
  if (!status.ok()) {
    return status;
  }
  return status;
}

Status Client::ListClusterNodes(const svk::ListClusterCommandRequest* req,
                                svk::ListClusterCommandResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->ListClusterNodes(&ctxt, *req, resp);
  if (!status.ok()) {
    return status;
  }
  return status;
}

Status Client::RegisterNode(const svk::RegisterRequest* req,
                            svk::RegisterResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->RegisterNode(&ctxt, *req, resp);
  if (!status.ok()) {
    return status;
  }
  return status;
}

Status Client::UnregisterNode(const svk::UnregisterRequest* req,
                              svk::UnregisterResponse* resp) {
  ClientContext ctxt;
  Status status = ctrlr_stub_->UnregisterNode(&ctxt, *req, resp);
  if (!status.ok()) {
    return status;
  }
  return status;
}
