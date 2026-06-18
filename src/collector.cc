#include "collector.h"

#include <unistd.h>
#include <zmq.h>

using namespace std;
inline const char *zmq_topic = "metric";

/**
 * @brief reads config file for zmq bind IP and port for host
 * @details This method takes json config file as input
 *          and parses for IP and port for the host for zmq binding.
 * @param conf_filename config file name.
 * @return returns the zmq bind address from host ip and port.
 */
string get_zmq_bindaddr(string conf_filename) {
  try {
    namespace pt = boost::property_tree;
    pt::ptree root;
    cout << "reading json config file = " << conf_filename << endl;
    pt::read_json(conf_filename, root);
    pt::ptree host_ip_info = root.get_child(SVK_CXL_HOST_TAG);
    string ip = host_ip_info.get<std::string>("ip", SVK_CXL_HOST_ZMQ_IP);
    string port = host_ip_info.get<std::string>("port", SVK_CXL_HOST_ZMQ_PORT);
    return "tcp://" + ip + ":" + port;
  } catch (const std::exception &e) {
    std::cerr << "Unable to read SVK host ip config. Error -> " << e.what()
              << '\n';
  }
  return "";
}

/**
* @brief run function which runs the collector
* @details This method takes collector object as input,
*          collector is run as a service thread, collects and publishes
           host metrics every COLLECTION_FREQUENCY_S seconds.
* @param collector object
* @return void
*/
void *_run(void *arg) {
  int rc = 0;
  string emsg = "Error in " + string(__FUNCTION__) + " : " +
                "##HOST_METRIC zmq_send failed, errno = " + to_string(errno) +
                "; error = " + strerror(errno);

  if (!arg) {
    cerr << "##HOST_METRIC collector run arg is null" << endl;
    return (char *)"##HOST_METRIC collector run arg is null";
  }

  cout << "##HOST_METRIC collector run function" << endl;
  Collector *c = static_cast<Collector *>(arg);

  string zmq_message;
  while (!c->stop_flag.load()) {
    try {
      rc = c->sys_metrics.get_system_metrics();
      if (rc == -1) {
        string msg = "Error in " + string(__FUNCTION__) + " : " +
                     "getting system metrics failed, rc = " + to_string(rc);
        cerr << msg << endl;
        if (c->stop_flag.load()) break;
        throw runtime_error(msg);
      }
      zmq_message =
          string(zmq_topic) + ":" + c->sys_metrics.metric_event_json_string;
      cout << "##HOST_METRIC zmq_send:" << zmq_message << endl;
      rc = zmq_send(c->c_pub, (void *)zmq_message.c_str(), zmq_message.length(),
                    0);
      if (rc == -1) {
        cerr << emsg << endl;
        throw runtime_error(emsg.c_str());
      }
      // Run every COLLECTION_FREQUENCY_S (5) seconds
      sleep(COLLECTION_FREQUENCY_S);
      if (TEST_BUILD) {
        throw runtime_error("test");
      }
    } catch (const std::runtime_error &e) {
      // Catch by const reference to handle specifically
      ++c_flag;
      cerr << c_flag << "::" << e.what() << endl;
    }
  }
  cout << "Collector thread exited" << endl;
  return (void *)(0);
}

int Collector::ServiceStart(void) {
  if (TEST_BUILD) {
    throw invalid_argument("test_ServiceStart");
  }
  return Service::ServiceStart();
}

void Collector::ServiceStop(void) {
  if (TEST_BUILD) {
    throw invalid_argument("test_ServiceStop");
  }
  cout << "Initiated to stop the collector thread" << endl;
  stop_flag.store(true);  // signal the loop to exit

  // Sleep twice the thread sleep interval for the data to push cleanly and exit
  sleep(2 * COLLECTION_FREQUENCY_S);

  // Forcefully close the socket to unblock any in-progress zmq_send and causes
  // it to return -1, which makes _run notice the stop_flag and break.
  if (c_pub) {
    zmq_close(c_pub);
    c_pub = nullptr;
  }
  if (c_context) {
    zmq_ctx_destroy(c_context);
    c_context = nullptr;
  }
  Service::ServiceStop();
}

/**
 * @brief collector constructor
 * @details This constructor creates collector object,
 *          creates zmq socket and binds to it.
 * @param bind_addr zmq bind address
 * @param svc_name collector
 * @param service function
 *
 */
Collector::Collector(string bind_addr, string svc_name,
                     void *(*svc_func)(void *arg))
    : Service(svc_name, svc_func) {
  int rc;
  c_context = zmq_ctx_new();
  c_pub = zmq_socket(c_context, ZMQ_PUB);

  // Release the port immediately on socket close so frequent restarts don't
  // hit EADDRINUSE during the OS TIME_WAIT period.
  int linger = 0;
  zmq_setsockopt(c_pub, ZMQ_LINGER, &linger, sizeof(linger));

  // Retry bind to overcome the TIME_WAIT (60s) time for the socket binded with
  // the port to be released by OS when the process goes down abruptly and
  // restarted. Retry for 10 times with 10s intervals
  constexpr int max_retries = 10;
  constexpr int retry_delay = 10;
  for (int attempt = 1; attempt <= max_retries; attempt++) {
    rc = zmq_bind(c_pub, bind_addr.c_str());
    if (rc == 0) {
      cout << "ZMQ bind successful to the address " << bind_addr << endl;
      break;
    }
    if (errno != EADDRINUSE || attempt == max_retries) {
      string msg = string("##HOST_METRIC zmq bind failed") + string(", rc: ") +
                   to_string(rc) + string(", errno: ") + strerror(errno);
      zmq_close(c_pub);
      zmq_ctx_destroy(c_context);
      throw runtime_error("Error in " + string(__FUNCTION__) + " : " + msg);
    }
    sleep(retry_delay);
  }
}

Collector::~Collector() {
  if (c_pub) {
    zmq_close(c_pub);
    c_pub = nullptr;
  }
  if (c_context) {
    zmq_ctx_destroy(c_context);
    c_context = nullptr;
  }
}

// Global collector object
Collector *c;

/**
 * @brief register collector service with service manager.
 * @param svc_mgr service manager object.
 * @return 0 on success
 */
int register_svk_service(ServiceManager *svc_mgr) {
  try {
    cout << "##HOST_METRIC Registering Collector service" << endl;
    string collector_pub_bind_addr;
    if (TEST_BUILD) {
      collector_pub_bind_addr = get_zmq_bindaddr(SVK_CXL_HOST_IP_CONFIG_TEST);
    } else {
      collector_pub_bind_addr = get_zmq_bindaddr(SVK_CXL_HOST_IP_CONFIG);
    }
    c = new Collector(collector_pub_bind_addr, "Collector", _run);
    if (svc_mgr == nullptr) {
      cerr << ("Error in " + string(__FUNCTION__) + " : " +
               string("svc_mgr:NULL"))
           << endl;
      return -1;
    }
    svc_mgr->ServiceAdd(c);
    return 0;
  } catch (const exception &e) {
    cout << "Error in " + string(__FUNCTION__) +
                " error in creating/registering service: " + e.what()
         << endl;
    return -2;
  }
}
