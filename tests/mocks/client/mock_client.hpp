#ifndef MOCK_CLIENT_HPP
#define MOCK_CLIENT_HPP

#include <gmock/gmock.h>

#include "client_library.h"

class FakeControllerClient : public Client {
 public:
  explicit FakeControllerClient(std::string node_name, std::string node_port)
      : Client(node_name, node_port) {
    std::cout << "FAKE CONTROLLER CLIENT CALLED" << std::endl;
    Client(node_name, node_port);
  }

  int GetChannelState(grpc_connectivity_state &state) {
    state = grpc_connectivity_state::GRPC_CHANNEL_READY;
    return 0;
  }

  int WaitForConnected() {
    std::cout << "WaitForConnected returning success" << std::endl;
    return 0;
  }
};

class FakeClient : public Client {
 public:
  explicit FakeClient(std::string node_name, std::string node_port)
      : Client(node_name, node_port) {}

  int GetChannelState(grpc_connectivity_state &state) {
    state = grpc_connectivity_state::GRPC_CHANNEL_READY;
    return 0;
  }
  Status ProcessNodeCommand(const svk::CommandRequest *req,
                            svk::CommandResponse *resp) {
    std::cout << "Mock processnodecommand called" << std::endl;
    // Mocking returning false to simulate no devices
    return Status(grpc::UNKNOWN, "Returning error to mock no devices in node");
  }
  int WaitForConnected() {
    std::cout << "WaitForConnected returning success" << std::endl;
    return 0;
  }
};

class MockFns {
 public:
  virtual ~MockFns() = default;
  virtual std::unique_ptr<Client> CreateClient(const std::string node_name,
                                               const std::string node_port) = 0;
};

class MockClient : public MockFns {
 public:
  MOCK_METHOD((std::unique_ptr<Client>), CreateClient,
              (const std::string node_name, const std::string node_port),
              (override));
};

extern MockClient *mockClient;

#endif  // MOCK_CLIENT_HPP
