#ifndef __CME_CONTEXT_H__
#define __CME_CONTEXT_H__

#include "cme_mover.h"
#include "cme_profiler.h"
#include <map>
#include <mutex>
#include <unordered_map>

using namespace std;

typedef enum ctx_state
{
        CTX_INACTIVE,
        CTX_ACTIVE
} ctx_state;

typedef enum stats_state
{
        STATS_INPROGRESS,
        STATS_DONE,
        STATS_INVALID
} stats_state;

/**
 * @brief structure for application parameters to relate to tuner context
 * @details tuner context :: tuner_element :: app_attrs
 * app name, app pid
 */
typedef struct app_attrs
{
  	string app_name;
  	long app_pid;
} app_attrs;

/**
 * @brief structure for application performance sla attrs
 * @details iops,i/o size, i/o latency
 */
typedef struct sla_attrs
{
  	unsigned long iops;
  	unsigned long sizebytes;
  	unsigned long latencyus;
} sla_attrs;

/**
 * @brief structure for host numa nodes for tiering
 */
typedef struct mem_attrs
{
  	int src_numa_node;
  	int dst_numa_node;
        int slow_tier;
  	int fast_tier;
} mem_attrs;

/**
 * @brief structure for host numa nodes for tiering
 */
typedef struct tm_attrs
{
  	std::string mover_tag;
  	std::string profiler_tag;
        enum cme_mover_aggr ag_level;
} tm_attrs;

/**
 * @brief cme_context class
 This class object is to represent a cme context.
 This is identified by app_name and app_pid pair.
 For any CME command that comes in for a particular
 app name and app pid pair this object keeps track of
 the associated operations objects(movers and profilers).
 same application pid.
 The context object can be deleted after a stop move/profile
 command if no other prior operations are in progress for the 
 application pid.

 A map of cme context objects is maintained in the cme_global object.
 */

class cme_context
{
public:
  	cme_context () = default;
  
  	cme_mover* mover_obj;
  	cme_profiler* profiler_obj;
  	app_attrs app_attr;
  	sla_attrs sla_attr;
  	mem_attrs mem_attr;
  	tm_attrs tm_attr;

  	/*
        This object state prevents multiple mover operations on the  
        same application pid.
        */ 

	ctx_state mover_state;
	
	/* 
        This maintains the status of the last mover operation command
        It will be used for get status command.
	*/ 
	int mover_cmd_status;

        /*
        state to keep track of get _stats in progress
        get stats will be async as time to completion is indeterminate with damo
        A similar approach to move_all()
        */ 
        stats_state get_stats_state;

  	string process_attributes(string);
  	string process_result(string);
};

#endif
