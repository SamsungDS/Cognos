#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/xml_parser.hpp>
#include <filesystem>
#include <iostream>
#include <map>
#include <stdexcept>
#include <tuple>
#include <unordered_map>
#include <vector>
#include "yaml-cpp/yaml.h"

#include "damo_main.h"
#include "damo_utils.h"
#include "cme_logger.h"

using namespace std;

/* Hard Coded Static config mapping from json file
 Local utility functions needed for generation of damo config yaml file to be
 used
*/
int read_damo_config_json(damo_config_params*, int);
static void populate_yaml(string, string, damo_config_params);
static void squash_promote_regions_yaml(string, string);
static string extract_damo_stats(vector<string> &, vector<string> &, string);
bool remove_context_yaml(string, string, string);
int yaml_generate();
int cgroup_create();
int cgroup_delete();

unordered_map<int, damo_config> damo_config_static_mappings;
damo_process_params damo_process_param;

int damo_init()
{
        int ret = 0;
        try
        {
                damo_config damo_config_filled;
                ret = read_damo_config_json(&(damo_config_filled.dem_conf), DAMO_DEMOTE);
                if (ret != 0)
                {
                        return ret;
                }
                ret = read_damo_config_json(&(damo_config_filled.pro_conf), DAMO_PROMOTE);
                if (ret != 0)
                {
                        return ret;
                }
                damo_config_static_mappings.try_emplace(damo_process_param.ag_level, damo_config_filled);
        }
        catch (const std::exception& e)
        {
                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : " + string(e.what()));
                ret = -EINVAL;
        }
        return ret;
}

/**
 * @brief function reads static mapping and populates damo config structure
 * @details
 * @params:
 *  input :damo_config_params structure
 *  input: damo action
 * @return: status of command execution
 */
int read_damo_config_json(damo_config_params* damo_config_params_to_fill, int damo_action)
{
        int ret;
        try
        {
                string conf_filename = SVK_DAMO_PATH + "damo_config.json";
                namespace pt = boost::property_tree;
                pt::ptree root;
                CME_LOG("INFO", "reading damo config json = ", conf_filename);
                pt::read_json(conf_filename, root);
                string damo_config_tag = "ag_level_" + to_string(damo_process_param.ag_level);
                pt::ptree damo_params = root.get_child(damo_config_tag);
                pt::ptree damo_action_node;
                if (damo_action == DAMO_DEMOTE)
                {
                        damo_action_node = damo_params.get_child("demotion_param");
                }
                else
                {
                        damo_action_node = damo_params.get_child("promotion_param");
                }

                damo_config_params_to_fill->intr_sample_us =
                damo_action_node.get<std::string>("intr_sample_us", "5 ms");
                damo_config_params_to_fill->intr_aggr_us =
                damo_action_node.get<std::string>("intr_aggr_us", "5 s");
                damo_config_params_to_fill->intr_ops_update_us =
                damo_action_node.get<std::string>("intr_ops_update_us", "10 s");
                damo_config_params_to_fill->nr_regions_min =
                damo_action_node.get<std::string>("nr_regions_min", "10,000");
                damo_config_params_to_fill->nr_regions_max =
                damo_action_node.get<std::string>("nr_regions_max", "100,000");
                damo_config_params_to_fill->quota_time_ms =
                damo_action_node.get<std::string>("quota_time_ms", "1 s");
                damo_config_params_to_fill->quota_sz_bytes =
                damo_action_node.get<std::string>("quota_sz_bytes", "50.000 GiB");
                damo_config_params_to_fill->quota_rst_intr_ms =
                damo_action_node.get<std::string>("quota_rst_intr_ms", "20 s");
                damo_config_params_to_fill->ap_nr_access_min =
                damo_action_node.get<std::string>("ap_nr_access_min", "50 %");
                damo_config_params_to_fill->ap_age_min =
                damo_action_node.get<std::string>("ap_age_min", "1000 ns");
                damo_config_params_to_fill->quota_wt_nr_acc_permil =
                damo_action_node.get<std::string>("quota_wt_nr_acc_permil", "100 %");
                ret = 0;
        }
        catch (const std::exception& e)
        {
                CME_ERR("Unable to read damo config json. Error -> ", e.what());
                ret = -EINVAL;
        }
        return ret;
}

/**
 * @brief function deletes damo config context based on cgroup_name
 * @details function deletes damo config context based on cgroup_name
 * It deletes all the kdamonds context matching the cgroup_name
 * @return: None
 */
bool remove_context_yaml(string input_file, string output_file, string cg_name)
{
        bool cleanup = false;
        try
        {
                YAML::Node config = YAML::LoadFile(input_file);
                YAML::Node kdamonds = config["kdamonds"];
                vector<int> to_remove_idx;
        
                for (long unsigned int i=0;i<kdamonds.size();i++)
                {    
                        YAML::Node contexts = kdamonds[i]["contexts"];
                        for (const auto& ops : contexts)
                        {
                                YAML::Node schemes = ops["schemes"];
                                for (const auto& action : schemes)
                                {
                                        YAML::Node filters = action["filters"];
                                        for (const auto& filter : filters)
                                        {
                                                if ((!(filter["filter_type"].as<string>().compare("memcg"))) && (!(filter["memcg_path"].as<string>().compare("/"+cg_name))))
                                                {
                                                        to_remove_idx.emplace_back(i);
                                                }
                                        }
                                }
                        }
                }
                for (long unsigned int i =0;i<to_remove_idx.size();i++)
                {
                        kdamonds.remove(to_remove_idx[i] -i);
                }
                YAML::Node kdamonds_ = config["kdamonds"];
                if (kdamonds_.size() == 0)
                {
                        cleanup = true;
                }

                std::ofstream fout(output_file);
                fout << config;
                fout.close();
                if (cleanup)
                {
                        string cmd = "printf \"%s\n\n\" \"$(sed '2,$d' " + output_file + ")\" > " + output_file;
                        vector<string> cmd_output;
                        int ret = execute_command(cmd, cmd_output, false);
                        if (ret)
                        {
                                throw runtime_error("Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                        }
                }
        }
        catch (const std::exception& e)
        {
                throw runtime_error("Error in " + string(__FUNCTION__) + " : " + string(e.what()));
        }
        return !(cleanup);
}

/**
 * @brief function creates cgroup
 * @details function mounts and creates cgroup based on application name and
 * application id
 * @return: status of command execution
 */
int cgroup_create()
{
        int ret = 0;
        try
        {
                string cmd;
                vector<string> cmd_output;

                cmd =
                "if mount | grep /sys/fs/cgroup; then echo 'CGROUP ALREADY MOUNTED'; "
                "else mount -t cgroup2 none /sys/fs/cgroup ; fi";
                ret = execute_command(cmd, cmd_output, TEST_BUILD);
                if (ret)
                {
                        CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                        return ret;
                }

                cmd_output.clear();
                cmd =
                "sudo echo '+memory' | sudo tee /sys/fs/cgroup/cgroup.subtree_control";
                ret = execute_command(cmd, cmd_output, TEST_BUILD);
                if (ret)
                {
                        CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                        return ret;
                }

                cmd_output.clear();
                cmd = "mkdir -p /sys/fs/cgroup/" + damo_process_param.cgoup_name;
                ret = execute_command(cmd, cmd_output, TEST_BUILD);
                if (ret)
                {
                        CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                        return ret;
                }

                cmd_output.clear();
                cmd =
                "echo " + damo_process_param.app_pid + " > /sys/fs/cgroup/" + damo_process_param.cgoup_name + "/cgroup.procs";
                ret = execute_command(cmd, cmd_output, TEST_BUILD);
                if (ret)
                {
                        CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                }
        }
        catch (const std::exception& e)
        {
                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : " + string(e.what()));
                ret = -EINVAL;
        }
        return ret;
}

/**
 * @brief function to generate damo config yaml file
 * @details function to generate damo config yaml file
 * @return: status of command execution
 */
int yaml_generate(int move_select)
{
        int ret = 0;
        try
        {
                string cmd;
                vector<string> cmd_output;
                string yaml_file =
                SVK_DAMO_PATH + damo_process_param.app_name + "_" + damo_process_param.app_pid + "_config.yaml";
                string yaml_file_promote =
                SVK_DAMO_PATH + damo_process_param.app_name + "_" + damo_process_param.app_pid + "_config_promote.yaml";
                string yaml_file_demote =
                SVK_DAMO_PATH + damo_process_param.app_name + "_" + damo_process_param.app_pid + "_config_demote.yaml";
                string yaml_file_promote_mod =
                SVK_DAMO_PATH + damo_process_param.app_name + "_" + damo_process_param.app_pid + "_config_promote_mod.yaml";
                string yaml_file_demote_mod =
                SVK_DAMO_PATH + damo_process_param.app_name + "_" + damo_process_param.app_pid + "_config_demote_mod.yaml";
                string ft = to_string(damo_process_param.fast_tier);
                string st = to_string(damo_process_param.slow_tier);
        
                // demote section config generation
                string cmd_demote = create_config_gen_command("d", ft, st, yaml_file_demote,
                                                                damo_process_param.app_name, damo_process_param.app_pid);
                execute_command(cmd_demote, cmd_output, false);
                if (ret)
                {
                        CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                        return ret;
                }
        
                // promote section config generation
                string cmd_promote;
                if (TEST_BUILD) {
                cmd_promote = create_config_gen_command("p", ft, st, yaml_file_promote,
                                                        damo_process_param.app_name, damo_process_param.app_pid);
                } else {
                cmd_promote = create_config_gen_command("p", st, ft, yaml_file_promote,
                                                        damo_process_param.app_name, damo_process_param.app_pid);
                }
        
                execute_command(cmd_promote, cmd_output, false);
                if (ret)
                {
                        CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                        return ret;
                }

                populate_yaml(yaml_file_demote, yaml_file_demote_mod,
                                damo_config_static_mappings[damo_process_param.ag_level].dem_conf);
                populate_yaml(yaml_file_promote, yaml_file_promote_mod,
                                damo_config_static_mappings[damo_process_param.ag_level].pro_conf);
                squash_promote_regions_yaml(yaml_file_promote_mod, yaml_file_promote_mod);
                
                // concat files
                if (move_select == MOVE)
                {
                        cmd = "printf \"%s\n\" \"$(cat " + yaml_file_demote_mod + ")\" > " + yaml_file;
                        ret = execute_command(cmd, cmd_output, false);
                        if (ret)
                        {
                                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                                return ret;
                        }
                        cmd = "printf \"\n\n%s\n\n\" \"$(sed '1d' " + yaml_file_promote_mod + ")\" >> " + yaml_file;
                        ret = execute_command(cmd, cmd_output, false);
                        if (ret)
                        {
                                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                                return ret;
                        }
                }
                else if (move_select == MOVE_HOT)
                {
                        cmd = "printf \"%s\n\n\" \"$(cat " + yaml_file_promote_mod + ")\" > " + yaml_file;
                        ret = execute_command(cmd, cmd_output, false);
                        if (ret)
                        {
                                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                                return ret;
                        }
                }
                else if (move_select == MOVE_COLD)
                {
                        cmd = "printf \"%s\n\n\" \"$(cat " + yaml_file_demote_mod + ")\" > " + yaml_file;
                        ret = execute_command(cmd, cmd_output, false);
                        if (ret)
                        {
                                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                                return ret;
                        }
                }
                else
                {
                        CME_ERR("Wrong move command");
                        ret = -EINVAL;
                }

                filesystem::path filePath(GLOBAL_DAMO_CONFIG);
        
                if (filesystem::exists(filePath))
                {
                        CME_LOG("INFO", "GLOBAL_DAMO_CONFIG File exists.\n");
                        cmd = "printf \"\n\n%s\n\n\" \"$(sed '1d' " + yaml_file + ")\" >> " + GLOBAL_DAMO_CONFIG;
                        ret = execute_command(cmd, cmd_output, false);
                        if (ret)
                        {
                                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                                return ret;
                        }
                }
                else
                {
                        CME_LOG("INFO", "GLOBAL_DAMO_CONFIG File does not exist.\n");
                        cmd = "printf \"%s\n\" \"$(cat " + yaml_file + ")\" > " + GLOBAL_DAMO_CONFIG;
                        ret = execute_command(cmd, cmd_output, false);
                        if (ret)
                        {
                                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                                return ret;
                        }
                }
                // Delete intermediate config yamls
                cmd = "rm -f " + yaml_file_promote + " " + yaml_file_demote + " " + yaml_file_promote_mod + " " + yaml_file_demote_mod + " " + yaml_file;
                ret = execute_command(cmd, cmd_output, false);
        }
        catch (const std::exception& e)
        {
                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : " + string(e.what()));
                ret = -EINVAL;
        }
        return ret;
}

/**
 * @brief function to squash adress regions for promote
 * @details function to squash adress regions for generated promote
 * config file.
 */
static void squash_promote_regions_yaml(string yaml_file_promote,
    string yaml_file_promote_mod)
{
        try
        {
                YAML::Node config = YAML::LoadFile(yaml_file_promote);
                YAML::Node kdamonds = config["kdamonds"];
                for (const auto& state : kdamonds)
                {
                        YAML::Node contexts = state["contexts"];
                        for (const auto& ops : contexts)
                        {
                                YAML::Node targets = ops["targets"];
                                for (const auto& pid : targets)
                                {
                                YAML::Node regions = pid["regions"];
                                string dd = regions[regions.size() - 1]["end"].as<string>();
                                regions[0]["end"] = dd;
                                int loopcount = regions.size();
                                for (int i = 0; i < loopcount; i++)
                                {
                                        regions.remove(1);
                                }
                                }
                        }
                }
                std::ofstream fout(yaml_file_promote_mod);
                fout << config;
                fout.close();
        }
        catch (const std::exception& e)
        {
                throw runtime_error("Error in " + string(__FUNCTION__) + " : " + string(e.what()));
        }
}

/**
* @brief function to populate damo config yaml file
* @details function to populate generated damo config yaml file
* with values from static mapping file based on parameters to
* start tuning command
*/
static void populate_yaml(
string yaml_file, string yaml_file_mod,
damo_config_params damo_cfg_param)  // param in is from sla struct , should
    // be called after yaml generate
{
        try
        {
                YAML::Node config = YAML::LoadFile(yaml_file);
                YAML::Node kdamonds = config["kdamonds"];
                for (const auto& state : kdamonds)
                {
                        YAML::Node contexts = state["contexts"];
                        for (const auto& ops : contexts)
                        {
                                YAML::Node intervals = ops["intervals"];
                                intervals["sample_us"] = damo_cfg_param.intr_sample_us;
                                intervals["aggr_us"] = damo_cfg_param.intr_aggr_us;
                                intervals["ops_update_us"] = damo_cfg_param.intr_ops_update_us;

                                YAML::Node nr_regions = ops["nr_regions"];
                                nr_regions["min"] = damo_cfg_param.nr_regions_min;
                                nr_regions["max"] = damo_cfg_param.nr_regions_max;

                                YAML::Node schemes = ops["schemes"];
                                for (const auto& action : schemes)
                                {
                                        YAML::Node ap = action["access_pattern"];
                                        ap["nr_accesses"]["min"] = damo_cfg_param.ap_nr_access_min;
                                        ap["age"]["min"] = damo_cfg_param.ap_age_min;
                                        YAML::Node quotas = action["quotas"];
                                        quotas["time_ms"] = damo_cfg_param.quota_time_ms;
                                        quotas["sz_bytes"] = damo_cfg_param.quota_sz_bytes;
                                        quotas["reset_interval_ms"] = damo_cfg_param.quota_rst_intr_ms;
                                        YAML::Node weights = quotas["weights"];
                                        weights["nr_accesses_permil"] = damo_cfg_param.quota_wt_nr_acc_permil;
                                }
                        }
                }

                std::ofstream fout(yaml_file_mod);
                fout << config;
                fout.close();
        }
        catch (const std::exception& e)
        {
                throw runtime_error("Error in " + string(__FUNCTION__) + " : " + string(e.what()));
        }
}

/**
 * @brief function to start damo pagemover
 * @details function to start damo pagemover:
 * does damo initialization steps, cgroup creation steps
 * damo config generation steps and then starts damo
 * @return: status of command execution
 */
int start(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level, int move_select)
{
        int ret = 0;
        try
        {
                damo_process_param.ag_level = aggresiveness_level;
                damo_process_param.fast_tier = fast_tier;
                damo_process_param.slow_tier = slow_tier;
                damo_process_param.cgoup_name = app_name + "_" + to_string(app_pid);
                damo_process_param.app_name = app_name;
                damo_process_param.app_pid = to_string(app_pid);

                
                ret = damo_init();
                if (ret)
                {
                        CME_LOG("INFO", "ERROR in damo init");
                        return ret;
                }
                string cmd;
                vector<string> cmd_output;
                cmd = "sudo " + PM_DAMO_PYTHON3_PATH + " " + PM_DAMO_PATH + " stop > /dev/null 2>&1";
                try
                {
                        ret = execute_command(cmd, cmd_output, false);
                }
                catch (const std::exception& e)
                {
                        CME_LOG("INFO", "damo not running");
                }


                ret = cgroup_create();
                if (ret)
                {
                        CME_LOG("INFO", "ERROR in cgroup creation");
                return ret;
                }

                ret = yaml_generate(move_select);
                if (ret)
                {
                        CME_LOG("INFO", "ERROR in damo config generation");
                return ret;
                }

                cmd = "sudo " + PM_DAMO_PYTHON3_PATH + " " + PM_DAMO_PATH + " start " + GLOBAL_DAMO_CONFIG;
                if (TEST_BUILD)
                {
                        ret = 0;
                }
                else
                {
                        ret = execute_command(cmd, cmd_output, false);
                        if (ret)
                        {
                                CME_LOG("INFO", "ERROR in damo start");
                        }
                }
        }
        catch (const std::exception& e)
        {
                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : " + string(e.what()));
                ret = -EINVAL;
        }
        return ret;
}
  
  /**
   * @brief function to delete created cgroup
   * @details unction to delete created cgroup
   * @return: status of command execution
   */
int cgroup_delete(string cg_name)
{
        int ret;
        try
        {
                string cmd;
                vector<string> cmd_output;

                cmd = "cgdelete -g memory:" + cg_name;
                ret = execute_command(cmd, cmd_output, TEST_BUILD);
                if (ret)
                {
                        CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                }

        }
    catch (const std::exception& e)
    {
        CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : " + string(e.what()));
        ret = -EINVAL;
    }
    return ret;
}
  
  /**
   * @brief function to stop damo pagemover
   * @details function to stop damo pagemover:
   * does damo initialization steps, cgroup deletion steps,
   * damo config file delete steps.
   * @return: status of command execution
   */
int stop(string app_name, long app_pid)
{
        int ret;
        try
        {
                string cmd;
                vector<string> cmd_output;
                cmd = cmd = "sudo " + PM_DAMO_PYTHON3_PATH + " " + PM_DAMO_PATH + " stop";
                ret = execute_command(cmd, cmd_output, TEST_BUILD);
                CME_LOG("INFO", "--damo--stop ", to_string(ret));
                if (ret)
                {
                        CME_LOG("INFO", "ERROR in command: ", cmd);
                        return -EINVAL;
                }

                string cg_name = app_name + "_" + to_string(app_pid);
                // remove corresponding contexts from global damo config and delete cgroup
                bool damon_context_exist = remove_context_yaml(GLOBAL_DAMO_CONFIG, GLOBAL_DAMO_CONFIG, cg_name);
                int ret = cgroup_delete(cg_name);
                if (ret)
                {
                        CME_LOG("INFO", "ERROR in cgroup_delete: ");
                        return ret;
                }

                // restart damo with remaining config
                if (damon_context_exist)
                {
                        cmd = "sudo " + PM_DAMO_PYTHON3_PATH + " " + PM_DAMO_PATH + " start " + GLOBAL_DAMO_CONFIG;
                        if (TEST_BUILD)
                        {
                                ret = 0;
                        }
                        else
                        {
                                ret = execute_command(cmd, cmd_output, false);
                                if (ret)
                                {
                                        CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : execute_command return value = " + to_string(ret));
                                        return ret;
                                }
                        }
                }
        }
        catch (const std::exception& e)
        {
                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : " + string(e.what()));
                ret = -EINVAL;
        }
        return 0;
}

/* 
read damo_report_params : create array/list of kdamon index and memcg name and action
read stats json file : get stats for relevant kdamon index: create json of memcg, action,stats : applied applied,qt exceeds
*/
static std::string extract_damo_stats(vector<string> &damon_stats_output, vector<string> &damon_params_output, string cg_name)
{
        try
        {
                namespace pt = boost::property_tree;
                pt::ptree root;
                pt::ptree result;
                string damo_json_string;
                for(auto s : damon_params_output)
                {
                        damo_json_string+=s;
                }
                        
                stringstream jsonStream(damo_json_string);       
                pt::read_json(jsonStream, root);
                
                unordered_map<string, string> kdamond_idx;
                int kd_idx = 0;
                for (const auto& item : root) 
                {
                        auto ctx =  item.second.get_child("contexts");
                        for (const auto& ctx_item : ctx)
                        {
                                auto schemes =  ctx_item.second.get_child("schemes");
                                for (const auto& sch_item : schemes)
                                {
                                        string action = sch_item.second.get<std::string>("action");
                                        auto filters =  sch_item.second.get_child("filters");
                                        for (const auto& filter : filters)
                                        {
                                                if ((!(filter.second.get<std::string>("filter_type").compare("memcg"))) && (!(filter.second.get<std::string>("memcg_path").compare("/"+cg_name))))
                                                {
                                                        kdamond_idx.try_emplace(to_string(kd_idx), action);
                                                }
                                        }
                                }
                        }
                        kd_idx++;
                }

                // get stats
                damo_json_string.clear();
                for(auto s : damon_stats_output)
                {
                        damo_json_string+=s;
                }
                stringstream jsonStream_stats(damo_json_string);            
                pt::read_json(jsonStream_stats, root);
                bool to_add;
                string kd = "";
                pt::ptree item_node;
                for (const auto& item : root)
                {
                        auto node = item.second.get_child("");
                        boost::property_tree::ptree node_add;
                        to_add = false;
                        string action;
                        for (auto it = node.begin(); it != node.end(); ++it)
                        {
                                for (auto it_ = it->second.begin(); it_ != it->second.end(); ++it_)
                                {
                                        if (it_->first == "kdamond")
                                        {
                                                kd = it_->second.data();
                                                if ((kdamond_idx.find(kd) != kdamond_idx.end()))
                                                {
                                                        to_add = true ;
                                                        action = kdamond_idx.at(kd);
                                                }
                                                break;
                                        }
                                        if (to_add)
                                        {
                                                if (it_->first == "nr_applied" || it_->first == "sz_applied" || it_->first == "qt_exceeds")
                                                {
                                                        boost::property_tree::ptree elem;
                                                        elem.put("", it_->second.data());
                                                        node_add.add_child(it_->first, elem);
                                                }
                                        }
                                }
                        }
                        if(node_add.size())
                        { 
                                item_node.add_child(action, node_add);
                        }
                }
                result.add_child(cg_name, item_node);

                std::ostringstream op;
                write_json(op, result);
                return op.str();
        }
        catch(const std::exception& e)
        {
                CME_ERR(e.what());
        }
        return "";
}

std::string get_stats(string app_name, long app_pid)
{
        try
        {
                if (TEST_BUILD)
                {
                        return "";
                }
                
                string cg_name = app_name + "_" + to_string(app_pid);
                vector<string> output_stats;
                vector<string> output_params;
                string command = "sudo " + PM_DAMO_PYTHON3_PATH + " " + PM_DAMO_PATH + " report damon --damos_stats --json";
                int ret = execute_command(command, output_stats, false);
                if (ret)
                {
                   CME_ERR("Error in " + string (__FUNCTION__) + "ERROR in command: " + command);
                   return to_string(ret);
                }
                command = "sudo " + PM_DAMO_PYTHON3_PATH + " " + PM_DAMO_PATH + " report damon --damon_params --json";
                ret = execute_command(command, output_params, false);
                if (ret)
                {
                   CME_ERR("Error in " + string (__FUNCTION__) + "ERROR in command: " + command);
                   return to_string(ret);
                }
                string res = extract_damo_stats(output_stats, output_params, cg_name);
                return res;
        }
        catch(const std::exception& e)
        {
                CME_ERR(e.what());
        }
        return "";
}
