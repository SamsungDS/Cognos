#ifndef __TUNER_H__
#define __TUNER_H__

#include <map>
#include <unordered_map>
#include <mutex>
#include "tuner_context.h"

const std::string GLOBAL_DAMO_CONFIG = "/etc/svk/global_damo_config.yaml";

/**
 * @brief struct to add hash function for a pair
 * @details When pair is used in an unordered_map, there is no 
* 	    default hash function, so we need to define one.
 */
struct pair_hash {
	template <class T1, class T2>
	std::size_t operator () (const std::pair<T1,T2> &p) const {
		auto h1 = std::hash<T1>{}(p.first);
		auto h2 = std::hash<T2>{}(p.second);
		return h1 ^ h2;  
	}
};

/**
 * @brief function to clean up global damo config
 * @details As cxl cleanup is not called in 
 * node service stop, need a clean up function.
 */
void damo_global_config_cleanup (void);

/**
 * @brief Tuner class
 * @details Tuner class to abstract memory tuning operations
 * members:
 *  global map for tuner commands context
 *  lock to protect global map
 *  start tuning and stop tuning implementation
 */
class tuner
{
	public:
		tuner();
		// golbal map of tuner contexts; key = (workload name, workload PID)
		unordered_map < pair<string, unsigned long>, tuner_context*, pair_hash > tuner_contexts;
		mutex tuner_mutex;
		int tuner_start(unordered_map<string, string>&, pm_type);
		int tuner_stop(pair <string, unsigned long>);
		void tuner_lock();
		void tuner_unlock();
};

#endif
