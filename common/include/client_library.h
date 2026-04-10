#ifndef __CLIENT_LIBRARY_H__
#define __CLIENT_LIBRARY_H__
#include <mutex>
#include <unordered_map>

#include "framework/framework.grpc.pb.h"
#include "grpc/health/v1/health.grpc.pb.h"
#include "grpc_hdr.h"

#define CONTROLLER_SERVICE_HEALTHCHECK_TAG "cognos_controller"
#define NODE_SERVICE_HEALTHCHECK_TAG "cognos_node"

// gRPC connection timeout for each command executed between controller to node
// server and vice-versa
#define GRPC_COMMAND_DEADLINE_TIMEOUT (180)

using grpc::health::v1::Health;
using grpc::health::v1::HealthCheckRequest;
using grpc::health::v1::HealthCheckResponse;
using svk::CommandFwk;
using svk::CommandRequest;
using svk::CommandResponse;
using svk::Controller;

struct ClientResources {
  std::shared_ptr<grpc::Channel> channel;
};

class Client {
 public:
  Client(const std::string& node, const std::string& port);
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
  virtual bool CheckServerHealth(const std::string& service_name);
  virtual int GetChannelState(grpc_connectivity_state& state);
  virtual int WaitForConnected();

 private:
  std::string node_and_port_;
  std::shared_ptr<Channel> channel_;
  std::unique_ptr<CommandFwk::Stub> fwk_stub_;
  std::unique_ptr<Controller::Stub> ctrlr_stub_;
  std::unique_ptr<Health::Stub> health_stub_;
};
#endif /* __CLIENT_LIBRARY_H__ */
