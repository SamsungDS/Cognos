#include <unistd.h>

#include <ctime>
#include <iostream>
#include <thread>

#include "libmock.h"

#define CFG "config/mock_config.json"
#define LOW_POLL 15
#define HIGH_POLL 120
#define CRITICAL_ERROR_COUNT 25

using namespace std;

enum cl_error {
  CL_OK,
  INVALID_COMMAND,
  NON_NUMERIC_NUMA_ID,
  INVALID_POLLING_INTERVAL,
  CL_END
};

void usage() {
  cout << "usage: ras_monitor -n <NUMA node ID> -i <polling interval>" << endl;
  return;
}

void printTime(string& res) {
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

int main(int argc, char* argv[]) {
  if (argc < 3) {
    usage();
    exit(INVALID_COMMAND);
  }

  int ret = 0, c;
  string dev = "", type = "correctable", tres;
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
  freopen("/dev/null", "a", stdout);
  ret = startup(CFG);
  freopen("/dev/tty", "a", stdout);

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
