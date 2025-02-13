#ifndef __TUNER_ELEMENT_H__
#define __TUNER_ELEMENT_H__

#include "jansson.h"
#include <bits/stdc++.h>
#include <ctime>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>

using namespace std;

/**
 * @brief enum for pagemover object state
 * @details for future use when we design state machine
 * present implementation just has one state PM_INIT
 */
typedef enum
{
  PM_INIT,
  PM_ACTIVE,
  PM_PAUSED,
  PM_STOPPED
} pm_state;

/**
 * @brief enum for pagemover type
 * @details for future use when we have multiple page movers
 * present implementation is done just for damo
 */
typedef enum pm_type
{
  PAGE_MOVER_DAMO,
  PAGE_MOVER_INVALID
} pm_type;

/**
 * @brief structure for application parameters to relate to tuner context
 * @details tuner context :: tuner_element :: app_params
 * app name, app pid
 */
typedef struct app_params
{
  string app_name;
  unsigned long app_pid;
} app_params;

/**
 * @brief structure for application performance sla params
 * @details iops,i/o size, i/o latency
 */
typedef struct sla_params
{
  unsigned long iops;
  unsigned long sizebytes;
  unsigned long latencyus;
} sla_params;

/**
 * @brief structure for page mover object details
 * @details presently page mover damo is only supported
 * for future use in state machine
 */
typedef struct pm_params
{
  int pm_state;
  bool pm_Persist;
  int pm_type;
} pm_params;

/**
 * @brief structure for host numa nodes for tiering
 * @details slow tier numa node , fast tier numa node
 * @todo for future , extend it to use int arrays for
 * multiple numa nodes in a tier support
 */
typedef struct host_memtiers
{
  int slow_tier;
  int fast_tier;
} host_memtiers;

/**
 * @brief class for tuner element
 * @details Parameters in start tuning command are stored in
 * this object
 * members: data structures for following:
 *  application parameters
 *  sla parameters
 *  pagemover parameters
 *  host memory parameters
 */
class tuner_element
{
public:
  // Default constructor
  tuner_element () = default;
  tuner_element (pm_state);
  app_params app_param;
  sla_params sla_param;
  pm_params pg_mvr;
  host_memtiers sys_param;
};

#endif
