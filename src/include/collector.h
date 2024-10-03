#ifndef __COLLECTOR_H__
#define __COLLECTOR_H__

#include "svc.h"
#include "svc_mgr.h"
#include "svc_mgr.h"
#include "metrics_collector.h"

const std::string SVK_CXL_HOST_TAG = "svk_cxl_host_node";
const std::string SVK_CXL_HOST_IP_CONFIG = "/etc/svk/zmq_config.json";
const std::string SVK_CXL_HOST_IP_CONFIG_TEST = "zmq_config.json";
const std::string SVK_CXL_HOST_ZMQ_IP = "127.0.0.1";
const std::string SVK_CXL_HOST_ZMQ_PORT = "5555";
const uint8_t COLLECTION_FREQUENCY_S = 5;


/**
 * @brief Collector class
 * @details This class derived from Service class.
 *          It holds the metrics collector object.
 *          It holds the zmq context.
 */
class Collector:public Service
{
	public:
		// default constructor
		Collector() = default;
		// parameterized constructor
		Collector(std::string bind_addr, std::string svc_name, void* (*svc_func)(void *arg));
		MetricsCollector sys_metrics;
		int ServiceStart(void);
		void ServiceStop(void);
		void            *c_pub;

	private:
		void            *c_context;
};

std::string get_zmq_bindaddr(std::string);

extern "C"
{
  int register_svk_service(ServiceManager *svc_mgr);
}
void* _run(void *arg);

#endif
