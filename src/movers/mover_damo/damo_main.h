#ifndef __DAMO_MAIN_H__
#define __DAMO_MAIN_H__

#include "mover_damo.h"

using namespace std;

const std::string SVK_DAMO_PATH = "/usr/local/svk/feature_modules/me/config/";
const std::string PM_DAMO_PATH = "/usr/local/svk/me/venv/bin/damo";
const std::string PM_DAMO_PYTHON3_PATH = "/usr/local/svk/me/venv/bin/python3";
const std::string PM_DAMO_CONFIG_GEN_SCRIPT = "tm_gen_config.py";
const std::string GLOBAL_DAMO_CONFIG = SVK_DAMO_PATH + "global_damo_config.yaml";

/**
 * @brief enum for damo action
 * @details damo action
 * presently supported: promote and demote
 */
enum damo_action
{
    DAMO_DEMOTE,
    DAMO_PROMOTE
};
  
enum move_select
{
    MOVE,
    MOVE_HOT,
    MOVE_COLD
};
/**
 * @brief structure for damo config params
 * @details damo config parameters that are read
 * static mapping file and populated into damo config.
 */
typedef struct damo_config_params
{
    string intr_sample_us;
    string intr_aggr_us;
    string intr_ops_update_us;
    string nr_regions_min;
    string nr_regions_max;
    string quota_time_ms;
    string quota_sz_bytes;
    string quota_rst_intr_ms;
    string ap_nr_access_min;
    string ap_age_min;
    string quota_wt_nr_acc_permil;

} damo_config_params;
  
/**
 * @brief structure for damo config
 * @details structure for promote and demote damo config
 */
typedef struct damo_config
{
    damo_config_params dem_conf;
    damo_config_params pro_conf;
} damo_config;

/**
 * @brief structure for damo params
 */
typedef struct damo_process_params
{
    string app_name;
    string app_pid;
    string cgoup_name;
    unsigned int slow_tier;
    unsigned int fast_tier;
    enum cme_mover_aggr ag_level;
} damo_process_params;

typedef tuple<string, long, long, long> workload_param;

int start(string, long, unsigned int, unsigned int, enum cme_mover_aggr, int);
int stop(string, long);
std::string get_stats(string app_name, long app_pid);
 
#endif