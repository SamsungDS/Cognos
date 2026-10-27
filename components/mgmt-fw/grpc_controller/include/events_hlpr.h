#ifndef __EVENTS_HLPR_H__
#define __EVENTS_HLPR_H__

#include "nlohmann/json.hpp"
#include "svk_logger.h"

using json = nlohmann::json;

const std::string cluster_create_event_msg = "Cluster created successfully";
const std::string cluster_delete_event_msg = "Cluster deleted successfully";
const std::string add_node_to_cluster_event_msg =
    "Node is added successfully to cluster";
const std::string remove_node_from_cluster_event_msg =
    "Node is successfully removed from the cluster";
const std::string node_online_event_msg = "Cognos Node service is online";
const std::string node_offline_event_msg = "Cognos Node service is offline";
const std::string hb_node_offline_event_msg =
    "Detected Cognos node service in offline mode";

int GenerateEventForClusterCreateSuccessful(const std::string& cluster_name,
                                            const std::string& node_name,
                                            json& event_json);

int GenerateEventForClusterDeleteSuccessful(const std::string& cluster_name,
                                            const std::string& node_name,
                                            json& event_json);

int GenerateEventForAddNodeToClusterSuccessful(const std::string& cluster_name,
                                               const std::string& node_name,
                                               json& event_json);

int GenerateEventForRemoveNodeFromClusterSuccessful(
    const std::string& cluster_name, const std::string& node_name,
    json& event_json);

int GenerateEventForNodeOnline(const std::string& cluster_name,
                               const std::string& node_name, json& event_json);

int GenerateEventForNodeOffline(const std::string& cluster_name,
                                const std::string& node_name, json& event_json);
int GenerateEventForDetectedNodeOfflineByHeartbeat(
    const std::string& cluster_name, const std::string& node_name,
    json& event_json);

#endif /*__EVENTS_HLPR_H__*/