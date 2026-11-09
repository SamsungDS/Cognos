#include "damo_utils.h"

#include <filesystem>

#include "pm_damo.h"

using namespace std;

string create_config_gen_command(string mode, string ft, string st,
                                 string filename, string app_name,
                                 string app_id) {
  string cmd;
  try {
    if (TEST_BUILD) {
      // if it is test, use global filter instead of cgroup based filter to
      // create damo config
      cmd = "sudo " + PM_DAMO_PYTHON3_PATH + " " + SVK_CXL_PATH +
            PM_DAMO_CONFIG_GEN_SCRIPT + " -" + mode + " " + ft + " " + st +
            " -g " + " -o " + filename;
    } else {
      // use cgroup based filter to create damo config
      cmd = "sudo " + PM_DAMO_PYTHON3_PATH + " " + SVK_CXL_PATH +
            PM_DAMO_CONFIG_GEN_SCRIPT + " -" + mode + " " + ft + " " + st +
            " -c " + app_name + "_" + app_id + " -o " + filename;
    }
  } catch (const exception& e) {
    throw runtime_error("Error in " + string(__FUNCTION__) + " : " +
                        string(e.what()));
  }
  return cmd;
}
