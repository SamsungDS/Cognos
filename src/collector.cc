#include "collector.h"

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
  int rc;
  string emsg = "Error in " + string(__FUNCTION__) + " : " +
                "##HOST_METRIC zmq_send failed, errno = " + to_string(errno) +
                "; error = " + strerror(errno);

  if (!arg) {
    cerr << "##HOST_METRIC collector run arg is null" << endl;
    return (char *)"##HOST_METRIC collector run arg is null";
  }

  cout << "##HOST_METRIC collector run function" << endl;

  string zmq_message;
  while (true) {
    try {
      Collector *c = static_cast<Collector *>(arg);
      rc = c->sys_metrics.get_system_metrics();
      if (rc == -1) {
        string msg = "Error in " + string(__FUNCTION__) + " : " +
                     "getting system metrics failed, rc = " + to_string(rc);
        cerr << msg << endl;
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
      sleep(
          COLLECTION_FREQUENCY_S);  // Run every COLLECTION_FREQUENCY_S seconds
      if (TEST_BUILD) {
        throw runtime_error("test");
      }
    } catch (const std::runtime_error &e) {
      // Catch by const reference to handle specifically
      ++c_flag;
      cerr << c_flag << "::" << e.what() << endl;
    }
  }
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
  rc = zmq_bind(c_pub, bind_addr.c_str());
  if (rc != 0) {
    string msg = string("##HOST_METRIC zmq bind failed") + string(", rc: ") +
                 to_string(rc);
    throw runtime_error("Error in " + string(__FUNCTION__) + " : " + msg);
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
