#include <unistd.h>

#include <ctime>
#include <iostream>
#include <thread>

#include "libmock.h"
#include "ras.hpp"

#define LOW_POLL 15
#define HIGH_POLL 120
#define CRITICAL_ERROR_COUNT 25
#define RAS_ERROR_INJECTION_MONITOR_LOG "/var/log/svk/ras_err_injection_monitor.log"

using namespace std;

enum cl_error {
  CL_OK,
  INVALID_COMMAND,
  NON_NUMERIC_NUMA_ID,
  INVALID_POLLING_INTERVAL,
  INVALID_FP,
  CL_END
};

void usage() {
  cout << "usage: ras_monitor -n <NUMA node ID> -i <polling interval>" << endl;
  return;
}

void printTime(string &res) {
  auto millis = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::system_clock::now().time_since_epoch())
                    .count() %
                1000;
  auto t = std::time(0);
  auto now = std::localtime(&t);
  char buffer[41];
  sprintf(buffer, "%04d-%02d-%02d %02d:%02d:%02d.%ld", now->tm_year + 1900,
          now->tm_mon + 1, now->tm_mday, now->tm_hour, now->tm_min, now->tm_sec,
          millis);
  res.assign(buffer);
}

svk_status parsing_ras_conf(std::string ras_conf_path, ras_conf *ras_configs) {
  boost::property_tree::ptree root_conf;
  static boost::property_tree::ptree logger_conf;
  try {
    boost::property_tree::read_json(ras_conf_path, root_conf);
  } catch (std::exception &e) {
    std::cout << "Unable to read ras config. Error -> " << e.what() << "."
              << std::endl
              << "Using the default config" << std::endl;
  }
  try {
    logger_conf = root_conf.get_child("ras.logger");
  } catch (std::exception &e) {
    std::cout << "Unable to read ras logger config. Error -> " << e.what()
              << "." << std::endl
              << "Using the default config" << std::endl;
  }
  ras_configs->log_file_name = logger_conf.get<std::string>(
      "log_file_name", RAS_LOGGER_FILE_NAME_DEFAULT);
  ras_configs->log_level =
      logger_conf.get<std::string>("log_level", RAS_LOGGER_LEVEL_DEFAULT);
  ras_configs->log_file_count =
      logger_conf.get<int>("log_file_count", RAS_LOGGER_FILE_COUNT_DEFAULT);
  ras_configs->log_file_size =
      logger_conf.get<int>("log_file_size", RAS_LOGGER_FILE_SIZE_DEFAULT);
  ras_configs->log_sink_type =
      logger_conf.get<std::string>("sink_type", RAS_LOGGER_SINK_TYPE_DEFAULT);

  return SVK_STATUS_SUCCESS;
}

int main(int argc, char *argv[]) {
  if (argc < 3) {
    usage();
    exit(INVALID_COMMAND);
  }

  /*  SVK initialize() */
  svk_status rc = SVK_STATUS_FAIL;
  std::string ras_conf_path;
  const char *env_p;
  if ((env_p = std::getenv("SVK_RAS_CONFIG")) != nullptr) {
    ras_conf_path = env_p;
  } else {
    ras_conf_path = RAS_CONFIG_FILE_DEFAULT;
  }
  ras_conf *ras_configs = new ras_conf();
  rc = parsing_ras_conf(ras_conf_path, ras_configs);
  if (rc != SVK_STATUS_SUCCESS) {
    return rc;
  }

  // Over-ride the log file name for this application
  ras_configs->log_file_name = RAS_ERROR_INJECTION_MONITOR_LOG;

  // initialization in the ras_logger_init function
  if (svk_logger_init(RAS_LOGGER, ras_configs->log_file_name.c_str(),
                      log_level_map.at(ras_configs->log_level),
                      ras_configs->log_file_count, ras_configs->log_file_size,
                      ras_configs->log_sink_type.c_str()) == 0) {
    svk_logger(RAS_LOGGER, level_E::INFO,
               "ras init called & logger is initialized");
  } else {
    std::cerr << "ras logger init fail" << std::endl;
    return SVK_STATUS_INVALID_CONFIG;
  }

  int ret = 0, c;
  string dev = "";
  string type = "correctable", tres;
  unsigned int interval = 5;

  while ((c = getopt(argc, argv, "n:i:h")) != -1) switch (c) {
      case 'n':
        for (size_t i = 0; i < strlen(optarg); ++i) {
          if (!isdigit(optarg[i])) {
            cout << "Invalid NUMA node ID provided. It should contain numeric "
                    "digits only."
                 << endl;
            usage();
            return NON_NUMERIC_NUMA_ID;
          }
        }
        dev = optarg;
        break;
      case 'i':
        for (size_t i = 0; i < strlen(optarg); ++i) {
          if (!isdigit(optarg[i])) {
            cout << "Invalid polling interval provided" << endl;
            usage();
            return INVALID_POLLING_INTERVAL;
          }
        }
        interval = stoi(optarg);
        if ((interval > 120) || (interval < 15)) {
          cout << "Polling interval should be between " << LOW_POLL << "-"
               << HIGH_POLL << " seconds." << endl;
          usage();
          return INVALID_POLLING_INTERVAL;
        }

        break;

      case 'h':
        usage();
        return CL_OK;
        break;
      default:
        usage();
        return INVALID_COMMAND;
        break;
    }

  // Response structure init
  Response res;

  // Disable syslog output during startup
  FILE *fp = freopen("/dev/null", "a", stdout);
  if (fp == nullptr) return INVALID_FP;

  ret = startup(nullptr);
  fp = freopen("/dev/tty", "a", stdout);
  if (fp == nullptr) return INVALID_FP;

  chrono::duration<int> interv(interval);
  int num_nodes = 0;

  while (1) {
    if (dev == "") {
      num_nodes = numa_max_node();

      for (int i = 0; i <= num_nodes; ++i) {
        dev = to_string(i);
        ret = getErrorCount(dev, type, res);
        if (ret == 0) {
          printTime(tres);
          cout << tres << " Error Count(" << dev << "):" << res.return_value
               << endl;
          if (stoi(res.return_value) > CRITICAL_ERROR_COUNT) {
            cout << " Error Count Threshold Crossed for NUMA node " << dev
                 << endl;
          }
        }
      }
      dev = "";
    } else {
      ret = getErrorCount(dev, type, res);
      if (ret == 0) {
        printTime(tres);
        cout << tres << " Error Count(" << dev << "):" << res.return_value
             << endl;
        if (stoi(res.return_value) > CRITICAL_ERROR_COUNT) {
          cout << " Error Count Threshold Crossed for NUMA node " << dev
               << endl;
        }
      }
    }
    cout << "++++++++++++++++++++" << endl;
    this_thread::sleep_for(interv);
  }

  return ret;
}
