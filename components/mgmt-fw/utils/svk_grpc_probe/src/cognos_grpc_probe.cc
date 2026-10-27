#include <arpa/inet.h>

#include <iostream>
#include <stdexcept>

#include "client_library.h"

/**
 * Validates an IP address.
 *
 * @param ip IP address to validate.
 * @return True if the IP address is valid, false otherwise.
 */
bool isValidIP(const std::string& ip) {
  struct in_addr addr;
  return inet_pton(AF_INET, ip.c_str(), &addr) == 1;
}

/**
 * Validates a port number.
 *
 * @param port Port number to validate.
 * @return True if the port number is valid, false otherwise.
 */
bool isValidPort(const std::string& port) {
  try {
    int portNum = std::stoi(port);
    return portNum >= 0 && portNum <= 65535;
  } catch (const std::invalid_argument& e) {
    return false;
  }
}

/**
 * Performs a health check on a specified service.
 *
 * @param ip IP address of the server.
 * @param port Port number of the server.
 * @param service_name Name of the service to check.
 * @return True if the service is healthy, false otherwise.
 */
bool checkServerHealth(const std::string& ip, const std::string& port,
                       const std::string& service_name) {
  // Input validation
  if (!isValidIP(ip)) {
    std::cerr << "Invalid IP address: " << ip << std::endl;
    return false;
  }

  if (!isValidPort(port)) {
    std::cerr << "Invalid port number: " << port << std::endl;
    return false;
  }

  if (service_name.empty()) {
    std::cerr << "Service name cannot be empty." << std::endl;
    return false;
  }

  try {
    Client client(ip, port);
    return client.CheckServerHealth(service_name);
  } catch (const std::exception& e) {
    std::cerr << "Error performing health check: " << e.what() << std::endl;
    return false;
  }

  return false;
}

int main(int argc, char* argv[]) {
  if (argc != 4) {
    std::cerr << "Usage: " << argv[0] << " <ip_addr> <port> <service_name>"
              << std::endl;
    return 1;
  }

  std::string ip = argv[1];
  std::string port = argv[2];
  std::string service_name = argv[3];

  bool isHealthy = checkServerHealth(ip, port, service_name);
  std::cout << "Service is " << (isHealthy ? "healthy" : "not healthy")
            << std::endl;

  return isHealthy ? 0 : 1;
}