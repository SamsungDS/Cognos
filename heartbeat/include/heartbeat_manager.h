#ifndef __HEARTBEAT_MANAGER_H__
#define __HEARTBEAT_MANAGER_H__

#include <atomic>
#include <chrono>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>

#include "client_library.h"

// Heartbeat health status enumeration
enum class HeartbeatStatus { UNKNOWN, HEALTHY, UNHEALTHY, TIMEOUT };

// Convert HeartbeatStatus to string
inline std::string heartbeat_status_to_string(HeartbeatStatus status) {
  switch (status) {
    case HeartbeatStatus::UNKNOWN:
      return "unknown";
    case HeartbeatStatus::HEALTHY:
      return "healthy";
    case HeartbeatStatus::UNHEALTHY:
      return "unhealthy";
    case HeartbeatStatus::TIMEOUT:
      return "timeout";
    default:
      return "unknown";
  }
}

// Convert string to HeartbeatStatus
inline HeartbeatStatus string_to_heartbeat_status(
    const std::string& status_str) {
  if (status_str == "healthy") return HeartbeatStatus::HEALTHY;
  if (status_str == "unhealthy") return HeartbeatStatus::UNHEALTHY;
  if (status_str == "timeout") return HeartbeatStatus::TIMEOUT;
  return HeartbeatStatus::UNKNOWN;
}

// Peer health status structure
struct PeerHealthStatus {
  std::string node_id;
  std::string ip;
  std::string port;
  std::string health_check_tag;
  HeartbeatStatus status;
  std::chrono::system_clock::time_point last_check_time;
  std::chrono::system_clock::time_point last_state_change_time;
  int failure_count;
  int success_count;

  PeerHealthStatus()
      : node_id(""),
        ip(""),
        port(""),
        health_check_tag(""),
        status(HeartbeatStatus::UNKNOWN),
        last_check_time(std::chrono::system_clock::now()),
        last_state_change_time(std::chrono::system_clock::now()),
        failure_count(0),
        success_count(0) {}

  PeerHealthStatus(const std::string& peer_node_id, const std::string& peer_ip,
                   const std::string& peer_port,
                   const std::string& health_check_tag)
      : node_id(peer_node_id),
        ip(peer_ip),
        port(peer_port),
        health_check_tag(health_check_tag),
        status(HeartbeatStatus::UNKNOWN),
        last_check_time(std::chrono::system_clock::now()),
        last_state_change_time(std::chrono::system_clock::now()),
        failure_count(0),
        success_count(0) {}
};

// Callback function type for health status changes
using HeartbeatCallback = std::function<void(
    const std::string& peer_node_id, const std::string& peer_ip,
    HeartbeatStatus old_status, HeartbeatStatus new_status)>;

// Heartbeat configuration
struct HeartbeatConfig {
  int check_interval_seconds;
  int timeout_seconds;
  int failure_threshold;
  int recovery_threshold;

  HeartbeatConfig()
      : check_interval_seconds(5),
        timeout_seconds(5),
        failure_threshold(3),
        recovery_threshold(2) {}
};

class HeartbeatManager {
 public:
  HeartbeatManager();
  explicit HeartbeatManager(const HeartbeatConfig& config);
  ~HeartbeatManager();

  // Start/stop heartbeat monitoring
  bool Start();
  void Stop();

  // Peer management
  bool AddPeer(const std::string& peer_node_id, const std::string& peer_ip,
               const std::string& peer_port,
               const std::string& health_check_tag = "");
  bool RemovePeer(const std::string& peer_node_id);

  // Status queries
  PeerHealthStatus GetPeerStatus(const std::string& peer_node_id);
  std::unordered_map<std::string, PeerHealthStatus> GetAllStatuses();

  // Callback registration
  void SetHealthCallback(HeartbeatCallback callback);

  // Configuration
  void SetConfig(const HeartbeatConfig& config);
  HeartbeatConfig GetConfig() const;

  // Check if manager is running
  bool IsRunning() const { return m_running.load(); }

 private:
  // Internal worker function for periodic health checks
  void HealthCheckWorker();

  // Check health of a single peer
  bool CheckPeerHealth(const std::string& peer_node_id,
                       const std::string& peer_ip, const std::string& peer_port,
                       const std::string& health_check_tag);

  // Update peer status and trigger callback if changed
  void UpdatePeerStatus(const std::string& peer_node_id,
                        const std::string& peer_ip,
                        const std::string& peer_port,
                        HeartbeatStatus new_status);

  // Generate peer key from node_id
  std::string MakePeerKey(const std::string& peer_node_id) const;

  HeartbeatConfig m_config;
  std::atomic<bool> m_running;
  std::unique_ptr<std::thread> m_health_check_thread;

  // Map of peer_key -> PeerHealthStatus
  std::unordered_map<std::string, PeerHealthStatus> m_peer_statuses;
  std::mutex m_peers_mutex;

  // Health check callback
  std::mutex m_callback_mutex;
  HeartbeatCallback m_health_callback;

  // Client cache for reusing connections
  std::unordered_map<std::string, std::unique_ptr<Client>>
      m_hb_mgr_client_cache;
  std::mutex m_client_mutex;
};

#endif /* __HEARTBEAT_MANAGER_H__ */
