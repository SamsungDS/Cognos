#ifndef __SVK_PUB_SUB_STRUCT_H__
#define __SVK_PUB_SUB_STRUCT_H__

#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

// Use the wildcard for the publisher. Subscriber needs to know the hostname/IP
// addr to connect
#define DEFAULT_PUB_IP_ADDR "0"
#define DEFAULT_PUB_SUB_PORT 5555
#define MAX_LENGTH 64

#define SVK_ZMQ_METRICS_FILTER_TOPIC "svk_zmq_metrics"
#define SVK_ZMQ_ALERTS_FILTER_TOPIC "svk_zmq_alerts"

// Moved from svk_zmq_api.h as this will be used for interfacing by the
// publisher This will be removed once the SLA tracker and controller changes
// are done.
typedef struct {
  char host_name[64];
  char app_name[64];
  char device_name[64];   // This may contain just numa of device
  uint64_t avgLatencyns;  // Latency in nanoseconds
  uint64_t iops;
  uint64_t bandwidthGBps;
  uint64_t avgReadLatency;
  uint64_t avgWriteLatency;
  uint64_t avgUpdateLatency;
  uint64_t avgReadIOPS;
  uint64_t avgWriteIOPS;
  uint64_t avgP99Latency;
  uint64_t ioBytesRead;
  uint64_t ioBytesWritten;
  uint64_t ioBytesRewrite;
} svk_slat_logic_output;

#endif /*__SVK_PUB_SUB_STRUCT_H__*/