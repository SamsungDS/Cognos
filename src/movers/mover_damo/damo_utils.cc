#include <filesystem>
#include <unistd.h>

#include "damo_utils.h"
#include "damo_main.h"

using namespace std;


int execute_command(string cmd, vector<string> &output, bool test_flag)
{
        cout << "Executing Command: " << cmd << endl;
        if (test_flag)
        {
                return 0;
        }
        try
        {
                char buffer[256];
                FILE* pipe = popen(cmd.c_str(), "r");
                if (!pipe)
                {
                        throw runtime_error("Error in " + string(__FUNCTION__) + " : error in popen for command: " + cmd);
                }
                while (fgets(buffer, sizeof(buffer), pipe) != nullptr)
                {
                        output.push_back(buffer);
                }
                int status = pclose(pipe);
                if (status != 0)
                {
                        throw runtime_error("Error in " + string(__FUNCTION__) + " : error in execution for command: " + cmd + " exit status: " + to_string(WEXITSTATUS(status)));
                }
        }
        catch (const exception& e)
        {
                throw runtime_error("Error in " + string(__FUNCTION__) + " : " + string(e.what()));
        }
        return 0;
}
  

string create_config_gen_command(string mode, string ft, string st,
                                 string filename, string app_name,
                                 string app_id)
{
        string cmd;
        try
        {
                if (TEST_BUILD)
                {
                // if it is test, use global filter instead of cgroup based filter to
                // create damo config
                cmd = "sudo " + PM_DAMO_PYTHON3_PATH + " " + SVK_DAMO_PATH + PM_DAMO_CONFIG_GEN_SCRIPT + " -" + mode + " " + ft + " " + st + " -g " + " -o " + filename;
                }
                else
                {
                // use cgroup based filter to create damo config
                cmd = "sudo " + PM_DAMO_PYTHON3_PATH + " " + SVK_DAMO_PATH + PM_DAMO_CONFIG_GEN_SCRIPT + " -" + mode + " " + ft + " " + st + " -c " + app_name + "_" + app_id + " -o " + filename;
                }
        }
        catch (const exception& e)
        {
                throw runtime_error("Error in " + string(__FUNCTION__) + " : " + string(e.what()));
        }
        return cmd;
}
