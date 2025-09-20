#ifndef _RAS_EVENT_PUBLISHER__HPP_
#define _RAS_EVENT_PUBLISHER__HPP_

#pragma once

#include "chrono"
#include "fmt/format.h"
#include "framework_extern.h"
#include "ras_exports.h"
#include "string"
#include "svk_logger.h"

namespace cognos::ras::publisher {
static const std::string ras_err_threshold_warning_template =
    "{{\"domain\": \"availability\", \"feature_name\": \"ras\", \"category\": "
    "\"health\", \"severity\": \"warning\", \"source\": {device_id}, "
    "\"source_type\": \"device\", \"timestamp\": {timestamp}, "
    "\"observations\": {{ \"message\" : \"{message}\" }} }}";

static int send_ras_threshold_warning_event(const std::string &device_id,
                                            const std::string &message) {
  auto time_stamp = std::chrono::duration_cast<std::chrono::seconds>(
                        std::chrono::system_clock::now().time_since_epoch())
                        .count();

  std::string event_json = fmt::format(
      cognos::ras::publisher::ras_err_threshold_warning_template,
      fmt::arg("device_id", device_id), fmt::arg("timestamp", time_stamp),
      fmt::arg("message", message));

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
