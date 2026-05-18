#ifndef __METRICS_COLLECTOR_H__
#define __METRICS_COLLECTOR_H__

#include <bits/stdc++.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <ctime>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "event.h"
#include "jansson.h"

const uint16_t METRIC_JSON_MAXLEN = 8192;

/**
 * @brief MetricsCollector class
 * @details MetricsCollector class.
 *          It holds the CPU and memory metrics c
 *
 */
class MetricsCollector {
 public:
  // Default constructor
  MetricsCollector() = default;

  Event metric_event;
  std::string metric_event_json_string;
  double system_cpu_current_usage;
  unsigned long long cxl_memory_capacity;
  unsigned long long dram_memory_capacity;
  unsigned long long cxl_memory_current_usage;
  unsigned long long dram_memory_current_usage;
  unsigned long long system_total_memory_capacity;
  unsigned long long system_total_memory_current_usage;
  std::string metrics_command_cpu;
  int get_system_metrics();
  void get_memory_metrics();
  void get_cpu_metrics();
  void populate_metric_event_fields(void);
  void generate_json(void);
};
#endif
