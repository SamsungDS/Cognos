#include "events_hlpr.h"

#include <google/protobuf/util/json_util.h>

#include <chrono>
#include <iomanip>
#include <sstream>

#include "events_hlpr.h"
#include "framework/events.pb.h"
#include "grpc_controller.h"

void PopulateBasicEventDetails(const std::string& cluster_name,
                               const std::string& node_name,
                               svk::EventData& event_data) {
  // Set event header
  svk::EventHeader* header = event_data.mutable_event_header();
  header->set_cluster_name(cluster_name);
  header->set_node_name(node_name);

  // Set event payload
  svk::EventPayload* payload = event_data.mutable_event_payload();
  payload->set_domain("configuration");
  payload->set_category("config");

  // Set timestamp in nanoseconds
  auto now = std::chrono::system_clock::now();
  auto nanos = std::chrono::duration_cast<std::chrono::nanoseconds>(
                   now.time_since_epoch())
                   .count();
  payload->set_timestamp(nanos);

  // Set timestamp_formatted in YYYY-MM-DD HH:MM AM/PM
  std::time_t now_c = std::chrono::system_clock::to_time_t(now);
  std::tm now_tm = *std::localtime(&now_c);
  std::ostringstream oss;
  oss << std::put_time(&now_tm, "%Y-%m-%d %I:%M %p");
  payload->set_timestamp_formatted(oss.str());
  return;
}

int ConvertProtoMessageToJsonData(const svk::EventData& event_data,
                                  json& event_json) {
  std::string json_output_str;
  google::protobuf::util::JsonPrintOptions options;
  int status = -1;
  std::string logger_str;

  // Optional: Configure output format
  options.add_whitespace = false;  // Pretty-print JSON
  options.always_print_primitive_fields =
      true;  // Include fields with default values
  options.preserve_proto_field_names =
      true;  // Use snake_case from .proto instead of camelCase

  auto msg_conv_status = google::protobuf::util::MessageToJsonString(
      event_data, &json_output_str, options);

  if (!msg_conv_status.ok()) {
    logger_str = "Failed to convert the proto message data to json. Error - " +
                 msg_conv_status.ToString();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return status;
  }

  // Not adding any checks as the JSON output coming from gRPC protobuf
  // message will be conformed to the JSON standards
  event_json = json::parse(json_output_str);
  status = 0;
  return status;
}

int GenerateBaseClusterManagementEvent(const std::string& cluster_name,
                                       const std::string& node_name,
                                       const std::string& msg,
                                       json& event_json) {
  svk::EventData event_data;
  PopulateBasicEventDetails(cluster_name, node_name, event_data);
  svk::EventPayload* payload = event_data.mutable_event_payload();
  payload->set_msg(msg);
  payload->set_severity("info");
  payload->set_source(cluster_name);
  payload->set_source_type("cluster");

  auto status = ConvertProtoMessageToJsonData(event_data, event_json);
  return status;
}

int GenerateBaseNodeManagementEvent(const std::string& cluster_name,
                                    const std::string& node_name,
                                    const std::string& severity,
                                    const std::string& msg, json& event_json) {
  svk::EventData event_data;
  PopulateBasicEventDetails(cluster_name, node_name, event_data);
  svk::EventPayload* payload = event_data.mutable_event_payload();
  payload->set_msg(msg);
  payload->set_severity(severity);
  payload->set_source(node_name);
  payload->set_source_type("node");

  auto status = ConvertProtoMessageToJsonData(event_data, event_json);
  return status;
}

int GenerateEventForClusterCreateSuccessful(const std::string& cluster_name,
                                            const std::string& node_name,
                                            json& event_json) {
  return GenerateBaseClusterManagementEvent(
      cluster_name, node_name, cluster_create_event_msg, event_json);
}

int GenerateEventForClusterDeleteSuccessful(const std::string& cluster_name,
                                            const std::string& node_name,
                                            json& event_json) {
  return GenerateBaseClusterManagementEvent(
      cluster_name, node_name, cluster_delete_event_msg, event_json);
}

int GenerateEventForAddNodeToClusterSuccessful(const std::string& cluster_name,
                                               const std::string& node_name,
                                               json& event_json) {
  return GenerateBaseClusterManagementEvent(
      cluster_name, node_name, add_node_to_cluster_event_msg, event_json);
}

int GenerateEventForRemoveNodeFromClusterSuccessful(
    const std::string& cluster_name, const std::string& node_name,
    json& event_json) {
  return GenerateBaseClusterManagementEvent(
      cluster_name, node_name, remove_node_from_cluster_event_msg, event_json);
}

int GenerateEventForNodeOnline(const std::string& cluster_name,
                               const std::string& node_name, json& event_json) {
  return GenerateBaseNodeManagementEvent(cluster_name, node_name, "info",
                                         node_online_event_msg, event_json);
}

int GenerateEventForNodeOffline(const std::string& cluster_name,
                                const std::string& node_name,
                                json& event_json) {
  return GenerateBaseNodeManagementEvent(cluster_name, node_name, "warning",
                                         node_offline_event_msg, event_json);
}

// Detected Cognos node service in offline mode
int GenerateEventForDetectedNodeOfflineByHeartbeat(
    const std::string& cluster_name, const std::string& node_name,
    json& event_json) {
  return GenerateBaseNodeManagementEvent(cluster_name, node_name, "warning",
                                         hb_node_offline_event_msg, event_json);
}
