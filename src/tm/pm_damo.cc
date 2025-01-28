#include "pm_damo.h"

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

#include "damo_utils.h"
#include "jansson.h"
#include "tuner.h"
#include "utils.h"
#include "yaml-cpp/yaml.h"

using namespace std;

// Hard Coded Static config mapping from json file
// Local utility functions needed for generation of damo config yaml file to be
// used
static void populate_yaml(string, string, damo_config_params);
static void squash_promote_regions_yaml(string, string);

int pm_damo::damo_init() {
  int ret;
  try {
    damo_config damo_config_1;
    ret = read_damo_config_json(&(damo_config_1.dem_conf), DAMO_DEMOTE);
    if (ret != 0) {
      return ret;
    }
    ret = read_damo_config_json(&(damo_config_1.pro_conf), DAMO_PROMOTE);
    if (ret != 0) {
      return ret;
    }
    workload_param wp_1;
    get<0>(wp_1) = mte->app_param.app_name;
    get<1>(wp_1) = mte->sla_param.iops;
    get<2>(wp_1) = mte->sla_param.sizebytes;
    get<3>(wp_1) = mte->sla_param.latencyus;
    damo_config_static_mappings[wp_1] = damo_config_1;
    ret = 0;
  } catch (const std::exception& e) {
    cout << "Error in " + string(__FUNCTION__) + " : " + string(e.what())
         << endl;
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
int pm_damo::read_damo_config_json(
    damo_config_params* damo_config_params_to_fill, int damo_action) {
  int ret;
  try {
    string conf_filename = SVK_CXL_PATH + "damo_config.json";
    namespace pt = boost::property_tree;
    pt::ptree root;
    cout << "reading damo config json = " << conf_filename << endl;
    pt::read_json(conf_filename, root);
    string app_name = mte->app_param.app_name;
    string sla_param_iops = to_string(mte->sla_param.iops);
    string sla_param_sz = to_string(mte->sla_param.sizebytes);
    string sla_param_lat = to_string(mte->sla_param.latencyus);
    string damo_config_tag_wkld_sla = app_name + "_" + sla_param_iops + "_" +
                                      sla_param_sz + "_" + sla_param_lat;
    pt::ptree damo_params = root.get_child(damo_config_tag_wkld_sla);
    pt::ptree damo_action_node;
    if (damo_action == DAMO_DEMOTE) {
      damo_action_node = damo_params.get_child("demotion_param");
    } else {
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
    ret = 0;
  } catch (const std::exception& e) {
    std::cerr << "Unable to read damo config json. Error -> " << e.what()
              << '\n';
    ret = -EINVAL;
  }
  return ret;
}

/**
 * @brief function creates cgroup
 * @details function mounts and creates cgroup based on application name and
 * application id
 * @return: status of command execution
 */
int pm_damo::cgroup_create() {
  int ret = 0;
  try {
    string cmd;
    vector<string> cmd_output;
    string app_name = mte->app_param.app_name;
    string app_id = to_string(mte->app_param.app_pid);
    string cgroup_name = app_name + "_" + app_id;

    cmd =
        "if mount | grep /sys/fs/cgroup; then echo 'CGROUP ALREADY MOUNTED'; "
        "else mount -t cgroup2 none /sys/fs/cgroup ; fi";
    execute_command(cmd, cmd_output, TEST_BUILD);

    cmd_output.clear();
    cmd =
        "sudo echo '+memory' | sudo tee /sys/fs/cgroup/cgroup.subtree_control";
    execute_command(cmd, cmd_output, TEST_BUILD);

    cmd_output.clear();
    cmd = "mkdir -p /sys/fs/cgroup/" + cgroup_name;
    execute_command(cmd, cmd_output, TEST_BUILD);

    cmd_output.clear();
    cmd =
        "echo " + app_id + " > /sys/fs/cgroup/" + cgroup_name + "/cgroup.procs";
    execute_command(cmd, cmd_output, TEST_BUILD);

    ret = 0;
  } catch (const std::exception& e) {
    cout << "Error in " + string(__FUNCTION__) + " : " + string(e.what())
         << endl;
    ret = -EINVAL;
  }
  return ret;
}

/**
 * @brief function to generate damo config yaml file
 * @details function to generate damo config yaml file
 * @return: status of command execution
 */
int pm_damo::yaml_generate() {
  int ret = 0;
  try {
    string cmd;
    vector<string> cmd_output;
    string app_name = mte->app_param.app_name;
    string app_id = to_string(mte->app_param.app_pid);
    string yaml_file = SVK_CXL_PATH + app_name + "_" + app_id + "_config.yaml";
    string yaml_file_promote =
        SVK_CXL_PATH + app_name + "_" + app_id + "_config_promote.yaml";
    string yaml_file_demote =
        SVK_CXL_PATH + app_name + "_" + app_id + "_config_demote.yaml";
    string yaml_file_promote_mod =
        SVK_CXL_PATH + app_name + "_" + app_id + "_config_promote_mod.yaml";
    string yaml_file_demote_mod =
        SVK_CXL_PATH + app_name + "_" + app_id + "_config_demote_mod.yaml";
    string ft = to_string(mte->sys_param.fast_tier);
    string st = to_string(mte->sys_param.slow_tier);

    // demote section config generation
    string cmd_demote = create_config_gen_command("d", ft, st, yaml_file_demote,
                                                  app_name, app_id);
    execute_command(cmd_demote, cmd_output, false);

    // promote section config generation
    string cmd_promote;
    if (TEST_BUILD) {
      cmd_promote = create_config_gen_command("p", ft, st, yaml_file_promote,
                                              app_name, app_id);
    } else {
      cmd_promote = create_config_gen_command("p", st, ft, yaml_file_promote,
                                              app_name, app_id);
    }

    execute_command(cmd_promote, cmd_output, false);

    workload_param wp =
        make_tuple(mte->app_param.app_name, mte->sla_param.iops,
                   mte->sla_param.sizebytes, mte->sla_param.latencyus);
    populate_yaml(yaml_file_demote, yaml_file_demote_mod,
                  damo_config_static_mappings[wp].dem_conf);
    populate_yaml(yaml_file_promote, yaml_file_promote_mod,
                  damo_config_static_mappings[wp].pro_conf);
    squash_promote_regions_yaml(yaml_file_promote_mod, yaml_file_promote_mod);

    // concat files
    cmd = "cat " + yaml_file_demote_mod + " > " + yaml_file;
    ret = execute_command(cmd, cmd_output, false);
    cmd = "echo >> " + yaml_file;
    ret = execute_command(cmd, cmd_output, false);
    cmd = "echo >> " + yaml_file;
    ret = execute_command(cmd, cmd_output, false);

    cmd = "awk FNR!=1 " + yaml_file_promote_mod + " >> " + yaml_file;
    ret = execute_command(cmd, cmd_output, false);
    cmd = "echo >> " + yaml_file;
    ret = execute_command(cmd, cmd_output, false);

    filesystem::path filePath(GLOBAL_DAMO_CONFIG);

    if (filesystem::exists(filePath)) {
      cout << "GLOBAL_DAMO_CONFIG File exists.\n";
      cmd = "awk FNR!=1 " + yaml_file + " >> " + GLOBAL_DAMO_CONFIG;
    } else {
      std::cout << "GLOBAL_DAMO_CONFIG File does not exist.\n";
      cmd = "cat " + yaml_file + " > " + GLOBAL_DAMO_CONFIG;
    }
    ret = execute_command(cmd, cmd_output, false);
    apply_damo_config_file = yaml_file;

    // Delete intermediate config yamls
    cmd = "rm -f " + yaml_file_promote + " " + yaml_file_demote + " " +
          yaml_file_promote_mod + " " + yaml_file_demote_mod;
    ret = execute_command(cmd, cmd_output, false);
  } catch (const std::exception& e) {
    cout << "Error in " + string(__FUNCTION__) + " : " + string(e.what())
         << endl;
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
                                        string yaml_file_promote_mod) {
  try {
    YAML::Node config = YAML::LoadFile(yaml_file_promote);
    YAML::Node kdamonds = config["kdamonds"];
    for (const auto& state : kdamonds) {
      YAML::Node contexts = state["contexts"];
      for (const auto& ops : contexts) {
        YAML::Node targets = ops["targets"];
        for (const auto& pid : targets) {
          YAML::Node regions = pid["regions"];
          string dd = regions[regions.size() - 1]["end"].as<string>();
          regions[0]["end"] = dd;
          int loopcount = regions.size();
          for (int i = 0; i < loopcount; i++) {
            regions.remove(1);
          }
        }
      }
    }
    std::ofstream fout(yaml_file_promote_mod);
    fout << config;
    fout.close();
  } catch (const std::exception& e) {
    throw runtime_error("Error in " + string(__FUNCTION__) + " : " +
                        string(e.what()));
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
  try {
    YAML::Node config = YAML::LoadFile(yaml_file);
    YAML::Node kdamonds = config["kdamonds"];
    for (const auto& state : kdamonds) {
      YAML::Node contexts = state["contexts"];
      for (const auto& ops : contexts) {
        YAML::Node intervals = ops["intervals"];
        intervals["sample_us"] = damo_cfg_param.intr_sample_us;
        intervals["aggr_us"] = damo_cfg_param.intr_aggr_us;
        intervals["ops_update_us"] = damo_cfg_param.intr_ops_update_us;

        YAML::Node nr_regions = ops["nr_regions"];
        nr_regions["min"] = damo_cfg_param.nr_regions_min;
        nr_regions["max"] = damo_cfg_param.nr_regions_max;

        YAML::Node schemes = ops["schemes"];
        for (const auto& action : schemes) {
          YAML::Node quotas = action["quotas"];
          quotas["time_ms"] = damo_cfg_param.quota_time_ms;
          quotas["sz_bytes"] = damo_cfg_param.quota_sz_bytes;
          quotas["reset_interval_ms"] = damo_cfg_param.quota_rst_intr_ms;
        }
      }
    }

    std::ofstream fout(yaml_file_mod);
    fout << config;
    fout.close();
  } catch (const std::exception& e) {
    throw runtime_error("Error in " + string(__FUNCTION__) + " : " +
                        string(e.what()));
  }
}

/**
 * @brief function to start damo pagemover
 * @details function to start damo pagemover:
 * does damo initialization steps, cgroup creation steps
 * damo config generation steps and then starts damo
 * @return: status of command execution
 */
int pm_damo::start() {
  int ret = 0;
  try {
    ret = damo_init();
    if (ret) {
      cout << "ERROR in damo init" << endl;
      return ret;
    }
    string cmd;
    vector<string> cmd_output;
    cmd = "sudo " + PM_DAMO_PYTHON3_PATH + " " + PM_DAMO_PATH +
          " stop > /dev/null 2>&1";
    try {
      ret = execute_command(cmd, cmd_output, false);
    } catch (const std::exception& e) {
      cout << "damo not running" << endl;
    }

    ret = cgroup_create();
    if (ret) {
      cout << "ERROR in cgroup creation" << endl;
      return -EINVAL;
    }

    ret = yaml_generate();
    if (ret) {
      cout << "ERROR in damo config generation" << endl;
      return -EINVAL;
    }

    cmd = "sudo " + PM_DAMO_PYTHON3_PATH + " " + PM_DAMO_PATH + " start " +
          GLOBAL_DAMO_CONFIG;
    if (TEST_BUILD) {
      ret = 0;
    } else {
      execute_command(cmd, cmd_output, false);
    }
  } catch (const std::exception& e) {
    cout << "Error in " + string(__FUNCTION__) + " : " + string(e.what())
         << endl;
    ret = -EINVAL;
  }
  return ret;
}

/**
 * @brief function to delete created cgroup
 * @details unction to delete created cgroup
 * @return: status of command execution
 */
int pm_damo::cgroup_delete() {
  int ret;
  try {
    string cmd;
    vector<string> cmd_output;
    string app_name = mte->app_param.app_name;
    string app_id = to_string(mte->app_param.app_pid);
    cmd = "cgdelete -g memory:" + app_name + "_" + app_id;
    if (TEST_BUILD) {
      ret = 0;
    } else {
      ret = execute_command(cmd, cmd_output, false);
    }
  } catch (const std::exception& e) {
    cout << "Error in " + string(__FUNCTION__) + " : " + string(e.what())
         << endl;
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
int pm_damo::stop() {
  int ret;
  try {
    string cmd;
    vector<string> cmd_output;
    cmd = "rm -f " + apply_damo_config_file;
    execute_command(cmd, cmd_output, false);
    cmd = cmd = "sudo " + PM_DAMO_PYTHON3_PATH + " " + PM_DAMO_PATH + " stop";
    ret = execute_command(cmd, cmd_output, false);
    if (ret) {
      cout << "ERROR in command: " << cmd << endl;
      ret = -EINVAL;
    }
    ret = 0;
  } catch (const std::exception& e) {
    cout << "Error in " + string(__FUNCTION__) + " : " + string(e.what())
         << endl;
    ret = -EINVAL;
  }
  return ret;
}
