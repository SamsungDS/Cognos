#ifndef __DAMO_MAIN_H__
#define __DAMO_MAIN_H__

using namespace std;

const std::string SVK_DAMO_PATH = "/usr/local/svk/feature_modules/me/config/";
const std::string PM_DAMO_PATH = "/usr/local/bin/damo";
const std::string PM_DAMO_PYTHON3_PATH = "/usr/bin/python3";
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
    unsigned int ag_level;
} damo_process_params;

typedef tuple<string, long, long, long> workload_param;
//int move(name, pid, slow_tier, fast_tier, aggresiveness_level) override;


int start(string, long, unsigned int, unsigned int, unsigned int, int);
int stop(string, long);
 
#endif