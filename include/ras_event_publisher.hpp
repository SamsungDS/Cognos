#ifndef _RAS_EVENT_PUBLISHER__HPP_
#define _RAS_EVENT_PUBLISHER__HPP_

#pragma once

#include <cstring>
#include <string>

#include "chrono"
#include "fmt/format.h"
#include "framework_extern.h"
#include "ras_exports.h"
#include "svk_logger.h"
namespace cognos::ras::publisher {

const int RAS_MAX_NODE_NAME_LENGTH = 256;
static std::string rasGetNodeName() {
  int len = RAS_MAX_NODE_NAME_LENGTH;
  svk_status status;

  // Note: Assuming the buffer is large enough to hold the node name.
  //       If the host name is longer than the buffer, the function will return
  //       empty string
  char buffer[RAS_MAX_NODE_NAME_LENGTH] = {0};

  status = get_node_name(buffer, &len);

  std::string result;
  if (status == SVK_STATUS_SUCCESS) {
    result = std::string(buffer, len);
  } else {
    svk_logger(RAS_LOGGER, level_E::WARN,
               fmt::format("get_node_name failed with error {error_code}\n",
                           fmt::arg("error_code", status))
                   .c_str());
  }

  return result;
}

static const std::string ras_err_threshold_warning_template =
    "{{\"domain\": \"availability\", \"feature_name\": \"ras\", \"tag\": "
    "\"{ras_event_tag}\", \"category\": \"health\", \"severity\": \"warning\", "
    "\"source\": \"{device_id}\", \"msg\" : \"{message}\",\"source_type\": "
    "\"device\", \"timestamp\": {timestamp}, \"observations\": {{ "
    "\"device_id\": \"{device_id}\", \"error_cnt\": {error_count} }} }}";

static std::string get_new_event_tag(const std::string &device_id) {
  auto epoch = std::chrono::duration_cast<std::chrono::nanoseconds>(
                   std::chrono::system_clock::now().time_since_epoch())
                   .count();
  std::string event_tag =
      fmt::format("{feat_name}_{node}_{device_id}_{epoch}",
                  fmt::arg("feat_name", RAS_FEATURE_MODULE_NAME),
                  fmt::arg("node", rasGetNodeName()),
                  fmt::arg("device_id", device_id), fmt::arg("epoch", epoch));
  return event_tag;
}

static int send_ras_threshold_warning_event(const std::string &device_id,
                                            const int error_count,
                                            const std::string &message) {
  auto time_stamp = std::chrono::duration_cast<std::chrono::nanoseconds>(
                        std::chrono::system_clock::now().time_since_epoch())
                        .count();

  std::string event_json = fmt::format(
      cognos::ras::publisher::ras_err_threshold_warning_template,
      fmt::arg("device_id", device_id), fmt::arg("timestamp", time_stamp),
      fmt::arg("error_count", error_count), fmt::arg("message", message),
      fmt::arg("ras_event_tag", get_new_event_tag(device_id)));

  int rc = publish_event_data_to_core((char *)"alerts",
                                      (uint8_t *)event_json.c_str(),
                                      (uint64_t)event_json.size());

  if (rc) {
    svk_logger(RAS_LOGGER, level_E::ALERT,
               fmt::format("Failed to publish RAS event for device: "
                           "{device_id} message: {message}",
                           fmt::arg("device_id", device_id),
                           fmt::arg("message", message))
                   .c_str());
  } else {
    svk_logger(RAS_LOGGER, level_E::ALERT,
               fmt::format("Published RAS threshold warning event for device: "
                           "{device_id} message: {message}",
                           fmt::arg("device_id", device_id),
                           fmt::arg("message", message))
                   .c_str());
  }

  return rc;
}
}  // namespace cognos::ras::publisher

#endif  // _RAS_EVENT_PUBLISHER__HPP_
