#ifndef __PM_DAMO_H__
#define __PM_DAMO_H__

#include "pagemover.h"

using namespace std;

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

struct TupleHash4
{
        template <typename T>
        std::size_t operator()(const T& tuple) const
        {
                return  std::hash<std::tuple_element_t<0, T>>{}(std::get<0>(tuple)) ^
                        std::hash<std::tuple_element_t<1, T>>{}(std::get<1>(tuple)) ^
                        std::hash<std::tuple_element_t<2, T>>{}(std::get<2>(tuple)) ^
                        std::hash<std::tuple_element_t<3, T>>{}(std::get<3>(tuple));
        }
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


typedef tuple<string,long,long,long> workload_param;

/**
 * @brief pm_damo class
 * @details derived class of pagemover class
 * implements start(), stop() functions holds 
 * the static mappings read from damo_config.json
 */
class pm_damo : public pagemover {
public:
        pm_damo() = default;
        int start();
        int stop();
        int damo_init();
        int read_damo_config_json(damo_config_params*, int);
        int cgroup_create();
        int cgroup_delete();
        int yaml_generate();
        string apply_damo_config_file;
        unordered_map <workload_param, damo_config, TupleHash4> damo_config_static_mappings;
};
#endif
