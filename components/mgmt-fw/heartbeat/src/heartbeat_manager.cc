#include "heartbeat_manager.h"

#include "svk_logger.h"

#ifndef HEARTBEAT_LOGGER_MODULE_NAME
#define HEARTBEAT_LOGGER_MODULE_NAME "DUMMYHB"
#endif

HeartbeatManager::HeartbeatManager() : m_running(false) {}

HeartbeatManager::HeartbeatManager(const HeartbeatConfig& config)
    : m_config(config), m_running(false) {}

HeartbeatManager::~HeartbeatManager() { Stop(); }

bool HeartbeatManager::Start() {
  if (m_running.load()) {
    std::string logger_str = "HeartbeatManager already running";
    svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::WARN, logger_str.c_str());
    return false;
  }

  m_running.store(true);
  m_health_check_thread =
      std::make_unique<std::thread>(&HeartbeatManager::HealthCheckWorker, this);

  std::string logger_str = "HeartbeatManager started with interval " +
                           std::to_string(m_config.check_interval_seconds) +
                           "s";
  svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());
  return true;
}

void HeartbeatManager::Stop() {
  if (!m_running.load()) {
    return;
  }

  m_running.store(false);

  if (m_health_check_thread && m_health_check_thread->joinable()) {
    m_health_check_thread->join();
  }
  m_hb_mgr_client_cache.clear();

  svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::INFO,
             "HeartbeatManager stopped");
}

bool HeartbeatManager::AddPeer(const std::string& peer_node_id,
                               const std::string& peer_ip,
                               const std::string& peer_port,
                               const std::string& health_check_tag) {
  std::string logger_str = "AddPeer called with " + peer_node_id + " (" +
                           peer_ip + ":" + peer_port +
                           ") with health check tag: " + health_check_tag;
  svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  std::lock_guard<std::mutex> lock(m_peers_mutex);
  std::string peer_key = MakePeerKey(peer_node_id);

  if (m_peer_statuses.find(peer_key) != m_peer_statuses.end()) {
    std::string logger_str =
        "Peer " + peer_node_id + " already exists in heartbeat manager";
    svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());
    return true;
  }

  PeerHealthStatus peer_node_status(peer_node_id, peer_ip, peer_port,
                                    health_check_tag);
  peer_node_status.status = HeartbeatStatus::HEALTHY;
  if (!health_check_tag.empty()) {
    std::string logger_str = "Added peer " + peer_node_id + " (" + peer_ip +
                             ":" + peer_port +
                             ") with health check tag: " + health_check_tag;
    svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());
  }

  m_peer_statuses[peer_key] = peer_node_status;

  // Create and cache a client for this peer
  std::lock_guard<std::mutex> client_lock(m_client_mutex);
  auto client = std::make_unique<Client>(peer_ip, peer_port);
  m_hb_mgr_client_cache[peer_key] = std::move(client);

  return true;
}

bool HeartbeatManager::RemovePeer(const std::string& peer_node_id) {
  std::lock_guard<std::mutex> lock(m_peers_mutex);

  std::string peer_key = MakePeerKey(peer_node_id);

  auto it = m_peer_statuses.find(peer_key);
  if (it != m_peer_statuses.end()) {
    std::string logger_str =
        "Removed peer " + peer_node_id + " from heartbeat manager";
    svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());
    m_peer_statuses.erase(it);
    return true;
  }

  return false;
}

PeerHealthStatus HeartbeatManager::GetPeerStatus(
    const std::string& peer_node_id) {
  std::lock_guard<std::mutex> lock(m_peers_mutex);

  std::string peer_key = MakePeerKey(peer_node_id);

  auto it = m_peer_statuses.find(peer_key);
  if (it != m_peer_statuses.end()) {
    return it->second;
  }

  return PeerHealthStatus();
}

std::unordered_map<std::string, PeerHealthStatus>
HeartbeatManager::GetAllStatuses() {
  std::lock_guard<std::mutex> lock(m_peers_mutex);
  return m_peer_statuses;
}

void HeartbeatManager::SetHealthCallback(HeartbeatCallback callback) {
  std::lock_guard<std::mutex> lock(m_callback_mutex);
  m_health_callback = std::move(callback);
}

void HeartbeatManager::SetConfig(const HeartbeatConfig& config) {
  m_config = config;
}

HeartbeatConfig HeartbeatManager::GetConfig() const { return m_config; }

std::string HeartbeatManager::MakePeerKey(
    const std::string& peer_node_id) const {
  return peer_node_id;
}

void HeartbeatManager::HealthCheckWorker() {
  std::string logger_str;
  svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::INFO,
             "Health check worker thread started");

  while (m_running.load()) {
    {
      svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::DEBUG,
                 "Waiting on acquiring mutex to check peer's healthcheck");
      std::lock_guard<std::mutex> lock(m_peers_mutex);
      svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::DEBUG,
                 "Waiting on acquiring mutex to check peer's healthcheck done");

      auto now = std::chrono::system_clock::now();

      for (auto& [peer_key, peer_node_status] : m_peer_statuses) {
        logger_str = "Check health for peer " + peer_node_status.node_id +
                     " ip: " + peer_node_status.ip +
                     " port:" + peer_node_status.port +
                     " health tag: " + peer_node_status.health_check_tag;
        svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::DEBUG,
                   logger_str.c_str());
        bool is_healthy = CheckPeerHealth(
            peer_node_status.node_id, peer_node_status.ip,
            peer_node_status.port, peer_node_status.health_check_tag);

        HeartbeatStatus new_status;
        if (is_healthy) {
          peer_node_status.success_count++;
          peer_node_status.failure_count = 0;
          logger_str =
              "Peer " + peer_node_status.node_id + " is healthy," +
              "success count:" + std::to_string(peer_node_status.success_count);
          svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::DEBUG,
                     logger_str.c_str());

          if (peer_node_status.status != HeartbeatStatus::HEALTHY &&
              peer_node_status.success_count >= m_config.recovery_threshold) {
            new_status = HeartbeatStatus::HEALTHY;
          } else {
            new_status = peer_node_status.status;
          }
        } else {
          peer_node_status.failure_count++;
          peer_node_status.success_count = 0;
          logger_str =
              "Peer " + peer_node_status.node_id + " is unhealthy," +
              "failure count:" + std::to_string(peer_node_status.failure_count);
          svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::ERROR,
                     logger_str.c_str());

          if (peer_node_status.status != HeartbeatStatus::UNHEALTHY &&
              peer_node_status.failure_count >= m_config.failure_threshold) {
            new_status = HeartbeatStatus::UNHEALTHY;
          } else {
            new_status = peer_node_status.status;
          }
        }

        peer_node_status.last_check_time = now;

        // Update status if changed
        if (new_status != peer_node_status.status) {
          logger_str = "UpdatePeerStatus called for Peer " +
                       peer_node_status.node_id + " is marked as " +
                       heartbeat_status_to_string(new_status);
          svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::INFO,
                     logger_str.c_str());
          UpdatePeerStatus(peer_node_status.node_id, peer_node_status.ip,
                           peer_node_status.port, new_status);
        }
      }
    }

    // Sleep for the configured interval
    std::this_thread::sleep_for(
        std::chrono::seconds(m_config.check_interval_seconds));
  }

  svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::INFO,
             "Health check worker thread exiting");
}

bool HeartbeatManager::CheckPeerHealth(const std::string& peer_node_id,
                                       const std::string& peer_ip,
                                       const std::string& peer_port,
                                       const std::string& health_check_tag) {
  std::string logger_str;
  std::lock_guard<std::mutex> client_lock(m_client_mutex);

  std::string peer_key = MakePeerKey(peer_node_id);

  // Get or create client for this peer
  auto it = m_hb_mgr_client_cache.find(peer_key);
  if (it == m_hb_mgr_client_cache.end()) {
    auto client = std::make_unique<Client>(peer_ip, peer_port);
    m_hb_mgr_client_cache[peer_key] = std::move(client);
    it = m_hb_mgr_client_cache.find(peer_key);
  }

  if (!it->second) {
    logger_str = "Client object not found in hb_mgr cache for node:" + peer_ip +
                 " port:" + peer_port;
    svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());
    return false;
  }

  return it->second->CheckServerHealth(health_check_tag);
}

void HeartbeatManager::UpdatePeerStatus(const std::string& peer_node_id,
                                        const std::string& peer_ip,
                                        const std::string& peer_port,
                                        HeartbeatStatus new_status) {
  std::string peer_key = MakePeerKey(peer_node_id);

  auto it = m_peer_statuses.find(peer_key);
  if (it == m_peer_statuses.end()) {
    return;
  }

  HeartbeatStatus old_status = it->second.status;
  it->second.status = new_status;
  it->second.last_state_change_time = std::chrono::system_clock::now();

  std::string logger_str = "Peer " + peer_node_id + " (" + peer_ip + ":" +
                           peer_port + ") health status changed from " +
                           heartbeat_status_to_string(old_status) + " to " +
                           heartbeat_status_to_string(new_status);
  svk_logger(HEARTBEAT_LOGGER_MODULE_NAME, level_E::INFO, logger_str.c_str());

  // Trigger callback if registered
  std::lock_guard<std::mutex> callback_lock(m_callback_mutex);
  if (m_health_callback) {
    m_health_callback(peer_node_id, peer_ip, old_status, new_status);
  }
}
