#ifndef __CLIENT_LIBRARY_H__
#define __CLIENT_LIBRARY_H__
#include "framework/framework.grpc.pb.h"
#include "grpc_hdr.h"

using svk::CommandFwk;
using svk::CommandRequest;
using svk::CommandResponse;
using svk::Controller;

class Client {
 public:
  Client(std::string node, std::string port);
  virtual ~Client() = default;
  virtual Status ProcessNodeCommand(const svk::CommandRequest* req,
                                    svk::CommandResponse* resp);
  virtual Status ProcessControllerCommand(const svk::CommandRequest* req,
                                          svk::CommandResponse* resp);
  virtual Status ListClusterNodes(const svk::ListClusterCommandRequest* req,
                                  svk::ListClusterCommandResponse* resp);
  virtual Status RegisterNode(const svk::RegisterRequest* req,
                              svk::RegisterResponse* resp);
  virtual Status UnregisterNode(const svk::UnregisterRequest* req,
                                svk::UnregisterResponse* resp);
  virtual Status SetNodeStatus(const svk::SetNodeStatusRequest* req,
                               svk::SetNodeStatusResponse* resp);
  virtual Status ClusterAPI(const svk::ClusterRequest* req,
                            svk::ClusterResponse* resp);
  virtual Status NodeAPI(const svk::NodeRequest* req, svk::NodeResponse* resp);
  virtual Status FeatureAPI(const svk::FeatureRequest* req,
                            svk::FeatureResponse* resp);
  virtual Status EventAPI(const svk::EventRequest* req,
                          svk::EventResponse* resp);
  virtual Status SLAManagementAPI(const svk::SLAManagementRequest* req,
                                  svk::SLAManagementResponse* resp);
  virtual Status StatsAPI(const svk::StatsRequest* req,
                          svk::StatsResponse* resp);

 private:
  std::shared_ptr<Channel> channel;
  std::unique_ptr<CommandFwk::Stub> fwk_stub_;
  std::unique_ptr<Controller::Stub> ctrlr_stub_;
};
#endif /* __CLIENT_LIBRARY_H__ */
