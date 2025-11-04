#ifndef __NODE_CMD_HELPER_FNS_H__
#define __NODE_CMD_HELPER_FNS_H__
#include "grpc_hdr.h"
#include "sla_hlpr_fns.h"

// Need to move these thresholds to JSON file for configuring
// until the actual settings are finalized
constexpr size_t ERROR_COUNT_THRESHOLD = 5;
constexpr size_t ERROR_RATE_THRESHOLD_COUNT = 3;
constexpr size_t ERROR_RATE_THRESHOLD_TIME_WINDOW_IN_SECS = 300;

// The "output" param is valid only if the command is successful. Check the
// value of return data structure "Status". if Status.ok() is true, the
// command is successful. Else it is failure and can check the error message
// using Status.error_message()
Status SendNodeCommand(const std::string& node_name,
                       const std::string& node_port,
                       const std::string& feature_name,
                       const std::string& command_name,
                       const std::string& command_params, std::string& output);

/**
 * @brief The function is used to enable tracking on the devices of the given
 * node
 * @param node_name Node IP address to send the command to
 * @param node_port Port number of the gRPC node server
 * @param ras_device_map A device map with the controller_generated_id as the
 * key and the DeviceInfo structure as the value
 *
 * @return 0 on success or -1 on failure
 */
int EnableRASTrackingOnDevices(
    const std::string& node_name, const std::string& node_port,
    const std::unordered_map<std::string, DeviceInfo>& ras_device_map);

/**
 * Disable the RAS tracking on this device.
 *
 * @return 0 if the device is disabled, -1 on failure.
 */

int DisableRASTrackingOnDevice(const std::string& node_name,
                               const std::string& node_port,
                               const std::string& device_id,
                               const std::string& device_type,
                               const std::string& device_numa);

#endif /*__NODE_CMD_HELPER_FNS_H__*/
