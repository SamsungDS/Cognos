#include "mock_client.hpp"

MockClient* mockClient;

const std::unique_ptr<Client> CreateClient(const std::string& node_name,
                                           const std::string& node_port) {
  if (mockClient)
    return mockClient->CreateClient(node_name, node_port);
  else
    return std::make_unique<Client>(node_name, node_port);
}
