#include <filesystem>
#include "tuner.h"
#include "pm_damo.h"

using namespace std;

tuner::tuner()
{
}

void tuner::tuner_lock()
{
        tuner_mutex.lock();
}

void tuner::tuner_unlock()
{
        tuner_mutex.unlock();
}

void damo_global_config_cleanup()
{
        filesystem::path filePath(GLOBAL_DAMO_CONFIG);

        if (filesystem::exists(filePath))
        {
                cout << "Global damo config File exists, deleting.\n";
                if (remove(GLOBAL_DAMO_CONFIG.c_str()) == 0)
                {
                        cout << "File: " + GLOBAL_DAMO_CONFIG + " deleted successfully." << endl;
                }
        }   
}

/**
 * @brief tuner start function to create tuner context and start pagemover
 * @details  creates tuner context and populates context fields based on parameters
 * to start tuning command. Adds contexxt to the global context map. 
 * Starts pagemover
 * @return Status of execution
 */
int tuner::tuner_start(unordered_map<string, string>& tokens_map, pm_type pgmv_type)
{
        int ret;
        try
        {
                pair <string, unsigned long> tuner_context_key = make_pair(tokens_map["application"], stoul(tokens_map["application_id"]));
                tuner_context* mtx;

                tuner_lock();
                if (tuner_contexts.find(tuner_context_key) != (tuner_contexts.end()))
                {
                        cout << "Memory tuning already active please use stop command before retrying" << endl;
                        tuner_unlock();
                        return -EBUSY;
                }
                else
                {
                        //if context does not exist in global tuner map, create and populate
                        mtx = new tuner_context(pgmv_type);
                        mtx->mte_obj->sys_param.fast_tier = stoi(tokens_map["dram_node"]);
                        mtx->mte_obj->sys_param.slow_tier = stoi(tokens_map["cxl_node"]);
                        mtx->mte_obj->sla_param.iops = stoul(tokens_map["sla_iops"]);
                        mtx->mte_obj->sla_param.sizebytes = stoul(tokens_map["sla_size"]);
                        mtx->mte_obj->sla_param.latencyus = stoul(tokens_map["sla_latencyus"]);
                        mtx->mte_obj->app_param.app_name = tokens_map["application"];
                        mtx->mte_obj->app_param.app_pid = stoul(tokens_map["application_id"]);
                        //Add entry to global context
                        tuner_contexts[tuner_context_key] = mtx; 
                        cout << "Context created: " << tuner_context_key.first << "_" << to_string(tuner_context_key.second)  << endl;
                }
                tuner_unlock();
                ret = tuner_contexts[tuner_context_key]->pm_obj->start();
                if (ret)
                {
                        cout << "ERROR in damo start " << endl;
                        ret =  -EINVAL;
                }
                else
                {
                        cout << "page mover started, state=" << to_string( tuner_contexts[tuner_context_key]->mte_obj->pg_mvr.pm_state) << endl;
                        ret = 0;
                }
        }
        catch(const std::exception& e)
        {
                cout << "Error in " + string(__FUNCTION__) + " : " + string(e.what()) << endl;
                ret =  -EINVAL;
                tuner_unlock();
        }
        return ret;
}

/**
 * @brief tuner stop function to stop page mover and clear tuner context.
 * @details  function to stop page mover and clear tuner context.
 * Stops pagemover, clears the context and it's associated data structures from global map
 * @return Status of execution
 */
int tuner::tuner_stop(pair <string, unsigned long> key_)
{
        int ret;
        try
        {
                tuner_lock();
                if (tuner_contexts.find(key_) != (tuner_contexts.end()))
                {
                        ret = tuner_contexts[key_]->pm_obj->stop();
                        // delete tuner context that was created at start; delete cortresponding objects ; delete global map entry
                        delete tuner_contexts[key_]->mte_obj;
                        delete tuner_contexts[key_]->pm_obj;
                        delete tuner_contexts[key_]; 
                        tuner_contexts.erase(key_); 
                        cout << "Context removed: " << key_.first << "_" << to_string(key_.second)  << endl;
                        if (ret)
                        {
                                cout << "ERROR in damo stop " << endl;
                                ret =  -EINVAL;
                        }
                        else
                        {
                                ret = 0;
                        }
                }
                else
                {
                        cout << "Memory tuner not found, please retry" << endl;
                        ret =  -EINVAL;
                }
        }
        catch(const std::exception& e)
        {
                cout << "Error in " + string(__FUNCTION__) + " : " + string(e.what()) << endl;
                ret =  -EINVAL;
        }
        tuner_unlock();
        return ret;
}
