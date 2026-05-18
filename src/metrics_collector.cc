#include "metrics_collector.h"

#include <numa.h>
#include <sys/wait.h>

#include <stdexcept>
using namespace std;

/**
* @brief trigger metrics collection
* @details This method is a top level function;
        It triggers individual functions for
        memory, cpu metrics collection, populate metric json
* @return 0 on success
*/
int MetricsCollector::get_system_metrics() {
  try {
    get_cpu_metrics();
    get_memory_metrics();
    populate_metric_event_fields();
    generate_json();
  } catch (const exception& e) {
    cerr << "Error in " + string(__FUNCTION__) + " : " + string(e.what())
         << endl;
    return -1;
  }
  return 0;
}

/**
 * @brief get host cpu metrics natively from /proc/stat
 * @details Reads kernel CPU counters over a 1-second interval.
 *          Includes a safe no-throw fallback if /proc/stat is unavailable.
 */
void MetricsCollector::get_cpu_metrics() {
  try {
    unsigned long long u1, n1, s1, i1, w1, ir1, so1, st1;
    unsigned long long u2, n2, s2, i2, w2, ir2, so2, st2;
    std::string label;

    // --- First Sample with Fallback Safety Check ---
    {
      std::ifstream file("/proc/stat");
      std::string line;
      if (std::getline(file, line)) {
        std::stringstream ss(line);
        ss >> label;
        if (label == "cpu") {
          ss >> u1 >> n1 >> s1 >> i1 >> w1 >> ir1 >> so1 >> st1;
        } else {
          throw std::runtime_error("Invalid layout inside /proc/stat");
        }
      }
    }

    // --- 1-Second Observation Window (Simulates dstat interval) ---
    std::this_thread::sleep_for(std::chrono::seconds(1));

    // --- Second Sample ---
    {
      std::ifstream file("/proc/stat");
      std::string line;
      if (std::getline(file, line)) {
        std::stringstream ss(line);
        ss >> label;
        if (label == "cpu") {
          ss >> u2 >> n2 >> s2 >> i2 >> w2 >> ir2 >> so2 >> st2;
        }
      }
    }

    // --- Math Computation Engine ---
    unsigned long long active_diff =
        (u2 + n2 + s2 + ir2 + so2 + st2) - (u1 + n1 + s1 + ir1 + so1 + st1);
    unsigned long long idle_diff = (i2 + w2) - (i1 + w1);
    unsigned long long total_diff = active_diff + idle_diff;

    if (total_diff == 0) {
      total_diff = 1;  // Division-by-zero protection ring
    }

    // Calculate dynamic usage matching: 100.0 - idle%
    double idle_pct = (static_cast<double>(idle_diff) * 100.0) /
                      static_cast<double>(total_diff);

    double cpu_usage = 100.0 - idle_pct;

    // Protect bounds against minor rounding artifacts
    if (cpu_usage < 0.0) cpu_usage = 0.0;
    if (cpu_usage > 100.0) cpu_usage = 100.0;

    // Directly assign back to your class state metric
    system_cpu_current_usage = cpu_usage;

  } catch (const std::exception& e) {
    // Keeps your exact required trace pattern for any other internal errors
    throw std::runtime_error("Error in " + std::string(__FUNCTION__) + " : " +
                             std::string(e.what()));
  }
}

static int bitmask_isallclear_bytes(struct bitmask* bm) {
  unsigned int bm_sz = numa_bitmask_nbytes(bm);
  unsigned bm_longs = bm_sz / sizeof(unsigned long);

  for (unsigned int i = 0; i < bm_longs; ++i) {
    unsigned long bm_long = bm->maskp[i];
    if (bm_long & 0xffffffff) return 0;
  }
  return 1;
}

/**
 * @brief get memory metrics
 * @details This method uses libnuma APIs to get numa node info
 *          and calculates DRAM/CXL capacity, usage and free metrics
 */
void MetricsCollector::get_memory_metrics(void) {
  try {
    const unsigned long long MB = 1024 * 1024;
    unsigned long long total_cxl_free = 0;
    unsigned long long total_cxl_size = 0;
    unsigned long long total_dram_free = 0;
    unsigned long long total_dram_size = 0;

    int numa_node_count = numa_num_configured_nodes();
    cout << "No of configured numa nodes found = " << numa_node_count << endl;
    int num_cpus_possible = numa_num_possible_cpus();
    int num_cpus_configured = numa_num_task_cpus();
    numa_set_localalloc();
    cout << "No of possible numa cpu count =" << num_cpus_possible << endl;
    cout << "No of configured numa cpu count =" << num_cpus_configured << endl;

    for (int i = 0; i < numa_node_count; i++) {
      unsigned long long sz;
      long long size_raw = numa_node_size64(i, (long long*)&sz);
      if (size_raw == (long long)-1) {
        throw runtime_error(
            "Error in getting numa node size : numa_node_size()");
      }
      unsigned long long size = size_raw / MB;
      unsigned long long free = sz / MB;
      cout << "numanode =" << i << " size=" << size << " free=" << free << endl;

      bitmask* mask = numa_bitmask_alloc(num_cpus_possible);
      if (mask == nullptr) {
        throw runtime_error(
            "Error in bit mask allocation : numa_allocate_cpumask ");
      }

      int st = numa_node_to_cpus(i, mask);
      if (st != 0) {
        throw runtime_error("Error in numa_node_to_cpus, errno = " +
                            to_string(errno) + ", error = " + strerror(errno));
      }
      if (bitmask_isallclear_bytes(mask)) {
        total_cxl_size += size;
        total_cxl_free += free;
      } else {
        total_dram_size += size;
        total_dram_free += free;
      }
      numa_bitmask_free(mask);
    }

    cout << "total dram size = " << total_dram_size
         << ", total dram free = " << total_dram_free
         << ", total dram usage = " << total_dram_size - total_dram_free
         << endl;
    cout << "total cxl size = " << total_cxl_size
         << ", total cxl free = " << total_cxl_free
         << ", total cxl usage = " << total_cxl_size - total_cxl_free << endl;

    cxl_memory_capacity = total_cxl_size;
    cxl_memory_current_usage = total_cxl_size - total_cxl_free;
    dram_memory_capacity = total_dram_size;
    dram_memory_current_usage = total_dram_size - total_dram_free;
    system_total_memory_capacity = total_cxl_size + total_dram_size;
    system_total_memory_current_usage =
        dram_memory_current_usage + cxl_memory_current_usage;
  } catch (const exception& e) {
    throw runtime_error("Error in " + string(__FUNCTION__) + " : " +
                        string(e.what()));
  }
}

/**
 * @brief populate metric event
 * @details This method populates the metric event fields
 */
void MetricsCollector::populate_metric_event_fields(void) {
  try {
    metric_event.type = "metric";
    char hostname[HOSTNAME_MAXLEN];
    gethostname(hostname, HOSTNAME_MAXLEN);
    string s(hostname);
    metric_event.source = s;
    metric_event.source_type = "application server";
    time_t now = std::time(0);
    tm* now_tm = std::gmtime(&now);
    char buf[size("yyyy-mm-ddThh:mm:ssZ")];
    strftime(buf, size("yyyy-mm-ddThh:mm:ssZ"), "%FT%TZ", now_tm);
    string s1(buf);
    metric_event.timestamp = s1;
    metric_event.category = "host system metrics";
    metric_event.description = "host cpu memory";
    metric_event.application = "cognos metric test";
    tuple<string, string> dram_cap;
    tuple<string, string> dram_usg;
    tuple<string, string> cxl_cap;
    tuple<string, string> cxl_usg;
    tuple<string, string> cpu_usg;
    dram_cap = make_tuple("dram_capacity_mb", to_string(dram_memory_capacity));
    dram_usg =
        make_tuple("dram_usage_mb", to_string(dram_memory_current_usage));
    cxl_cap = make_tuple("cxl_capacity_mb", to_string(cxl_memory_capacity));
    cxl_usg = make_tuple("cxl_usage_mb", to_string(cxl_memory_current_usage));
    cpu_usg = make_tuple("cpu_usage", to_string(system_cpu_current_usage));
    metric_event.observations.push_back(dram_cap);
    metric_event.observations.push_back(dram_usg);
    metric_event.observations.push_back(cxl_cap);
    metric_event.observations.push_back(cxl_usg);
    metric_event.observations.push_back(cpu_usg);
  } catch (const exception& e) {
    throw runtime_error("Error in " + string(__FUNCTION__) + " : " +
                        string(e.what()));
  }
}

/**
* @brief generates the metric event json
* @details This method creates the json object from metric event object;
                   It creates the json string for zmq publish.
*/
void MetricsCollector::generate_json(void) {
  try {
    json_t* metric_event_fields = json_object();
    json_t* jtemp = nullptr;
    jtemp = json_string(metric_event.type.c_str());
    json_object_set_new(metric_event_fields, "type", jtemp);
    jtemp = json_string(metric_event.source.c_str());
    json_object_set_new(metric_event_fields, "source", jtemp);
    jtemp = json_string(metric_event.source_type.c_str());
    json_object_set_new(metric_event_fields, "source_type", jtemp);
    jtemp = json_string(metric_event.timestamp.c_str());
    json_object_set_new(metric_event_fields, "timestamp", jtemp);
    jtemp = json_string(metric_event.description.c_str());
    json_object_set_new(metric_event_fields, "description", jtemp);
    jtemp = json_string(metric_event.category.c_str());
    json_object_set_new(metric_event_fields, "category", jtemp);
    jtemp = json_string(metric_event.application.c_str());
    json_object_set_new(metric_event_fields, "application", jtemp);
    json_t* metric_observations_fields = json_object();
    json_object_set_new(metric_event_fields, "observations",
                        metric_observations_fields);
    for (auto item : metric_event.observations)  // item is a tuple
    {
      if (get<0>(item).compare("cpu_usage") == 0) {
        jtemp = json_real(stod(get<1>(item)));
      } else {
        jtemp = json_integer(stoull(get<1>(item)));
      }
      json_object_set_new(metric_observations_fields, get<0>(item).c_str(),
                          jtemp);
    }
    char event_metrics_json[METRIC_JSON_MAXLEN];
    char* buf = event_metrics_json;
    buf = json_dumps(metric_event_fields, METRIC_JSON_MAXLEN);
    string temp_json(buf);
    metric_event_json_string = temp_json;
  } catch (const exception& e) {
    throw runtime_error("Error in " + string(__FUNCTION__) + " : " +
                        string(e.what()));
  }
}
