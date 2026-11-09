#include <iostream>
#include <map>
#include <stdexcept>
#include <tuple>
#include <map>
#include <unordered_map>
#include <dlfcn.h>
#include <dirent.h>
#include <vector>
#include <errno.h>
#include <sys/inotify.h>
#include <sys/stat.h>
#include <thread>
#include <functional>
#include <memory>
#include <chrono>
#include <unistd.h>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/xml_parser.hpp>
#include <filesystem>

#include "cme_global.h"
#include "cme_logger.h"

using namespace std;

cme_global::cme_global() {}

/**
 * @brief Helper function to read cme_config json file
 *      Extract path for shared li=brary location for
 *      profilers and movers.
 * @param: 
 *      string: cme_config file name
 * @return int: status = success/failure
*/
int cme_global::read_cme_config_json (std::string conf_filename)
{
	try
	{
      		namespace pt = boost::property_tree;
		pt::ptree root;
      		CME_LOG("INFO" , "reading cme config json = " , conf_filename);
      		pt::read_json (conf_filename, root);

      		profilers_lib = root.get<std::string> ("profilers_lib_path");
      		movers_lib = root.get<std::string> ("movers_lib_path");
      		CME_LOG("INFO" , profilers_lib , " -- ", movers_lib);
    	}
  	catch (const std::exception &e)
    	{
      		CME_ERR("Unable to read cme config json. Error -> " , e.what ());
      		return -EINVAL;
    	}
  	return 0;
}

void cme_global::mover_register(std::string mover_name, cme_mover* mover_obj)
{
        movers_list.try_emplace(mover_name, mover_obj);
}

void cme_global::profiler_register(std::string profiler_name, cme_profiler* profiler_obj)
{
                profilers_list.try_emplace(profiler_name, profiler_obj);
}

/**
 * @brief Discover profilers or movers through
 * 	dynamic loading of shared library objects.
 * 	Populate global list of movers and profilers
 * @param: 
 * 	string: directory path of shared libraries
 * 	enum: cme_type = profiler/mover
 * @return int: status = success/failure
*/
int cme_global::_cme_discovery(std::string feat_sm_svcs_dir, int type)
{
        try
        {
                CME_LOG("INFO", "cme discovery in path = ", feat_sm_svcs_dir);
                DIR *dirfp = opendir(feat_sm_svcs_dir.c_str());

                if (dirfp == nullptr)
                {
                        CME_LOG("INFO", "Invalid feature service directory");
                        return -EINVAL;
                }

                struct dirent *entry = readdir(dirfp);
                for (; entry != nullptr; entry = readdir(dirfp))
                {
                        std::string entry_name(entry->d_name);
                        std::string feat_lib_suffix_so(".so");
                        if (entry_name.compare(".") == 0 || entry_name.compare("..") == 0) continue;
                        std::string dfpath = feat_sm_svcs_dir + std::string("/") + entry_name;
                        if (isDirectory(dfpath)) _cme_discovery(dfpath, type);
                        if (entry_name.size() < feat_lib_suffix_so.size() ||
                        entry_name.compare(entry_name.size() - feat_lib_suffix_so.size(),
                                                feat_lib_suffix_so.size(),
                                                feat_lib_suffix_so) != 0) {
                        	CME_LOG("INFO", "No Service found");
                        	continue;
                        }

                        std::string feature_lib_str = feat_sm_svcs_dir + "/" + entry_name;
                        void *handle = dlopen(feature_lib_str.c_str(), RTLD_LAZY);
                        if (!handle)
                        {
                                CME_ERR("Failed to load library ", feature_lib_str, " Reason: ", dlerror());
                                continue;
                        }

                        if (type == CME_MOVER)
                        {
                                auto register_cme_fn = reinterpret_cast<cme_mover* (*)()>(dlsym(handle, "register_cme_fn"));
                                if (!register_cme_fn) {
                                        CME_ERR("Cannot load symbols from library ", feature_lib_str, " Reason: ", dlerror());
                                        dlclose(handle);
                                        return 1;
                                }
                                cme_mover* cme_obj = register_cme_fn();
                                if (!cme_obj) {
                                        CME_ERR("Object creation failed");
                                        dlclose(handle);
                                        continue;
                                }
				mover_register(cme_obj->get_name(), cme_obj);
                        }
                        else
                        {
                                throw runtime_error ("Error in " + string (__FUNCTION__) + " Invalid CME type");
                        }
                }
        }

        catch (const std::exception &e)
        {
                CME_ERR("Error in cme discovery: Error -> ", e.what ());
                return -EINVAL;
        }
        return 0;
}


/**
 * @brief Discover profilers and movers
 * @return int: status = success/failure
*/
int cme_global::cme_discovery()
{
        int rc1;
        try
        {
                rc1 = _cme_discovery(movers_lib, CME_MOVER);
                if (rc1 !=0)
                {
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " cme_discovery failed for : " + movers_lib);
                }
        }
        catch (const std::exception &e)
        {
                CME_ERR("cme_discovery. Error -> ", e.what ());
                return -EINVAL;
        }
	CME_LOG("INFO", "Movers discovered count = " , movers_list.size());
	return 0;
}

void cme_global::cme_contexts_lock ()
{
        cme_contexts_mutex.lock ();
}

void cme_global::cme_contexts_unlock ()
{
        cme_contexts_mutex.unlock ();
}

/**
 * @brief find cme_context based on context key
 * 	that is app name and app_pid,
 * 	If context not present, create cme_context and
 * 	populate relevant members.
 * @param cme_global object, command tokens map,
 * @return cme_context object
*/
cme_context* cme_global::cg_find_context(unordered_map<string, string> &tokens_map, bool read_only)
{
        try 
        {
		std::string app_name = tokens_map.at("app");
                long app_pid = stol (tokens_map.at("app_pid"));

                std::pair<std::string, long> cme_ctx_key = make_pair (app_name, app_pid);
                cme_context* cme_ctx;
                // Check if the element was found
                if (cme_contexts_list.find(cme_ctx_key) != (cme_contexts_list.end ()))
                {
                        CME_LOG("INFO", "cme context found for key:"  , cme_ctx_key.first , "_" , to_string(cme_ctx_key.second));
                        cme_ctx = cme_contexts_list.at(cme_ctx_key);
                }
                else
                {
                        if (read_only)
                        {
                                return nullptr;
                        }
                        // create new context
                        cme_ctx = new cme_context ();
                        cme_ctx->app_attr.app_name = app_name;
                        cme_ctx->app_attr.app_pid  = app_pid;
			cme_ctx->mover_state = CTX_INACTIVE;
                        cme_ctx->get_stats_state = STATS_INVALID;

                        // Add context to list
                        cme_contexts_list.try_emplace(cme_ctx_key,cme_ctx);
                }
                // Update tag for context
                cme_ctx->event_tag = tokens_map.at("tag");
                return cme_ctx;
        }
        catch (const std::exception &e)
        {
                CME_ERR("cg_find_context. Error -> ", e.what ());
                return nullptr;
        }
}

/**
 * @brief find mover from global movers list
 *      Can be expanded later to add more intelligent logic
 * @param cme_global object,
 *        cme_context pointer
 * @return cme_mover object
*/
cme_mover* cme_global::cg_find_mover(cme_context* cme_ctx)
{

        cme_mover* cme_mov;
        try
        {
                if (movers_list.empty())
                {
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " No movers found ");
                }
                if(cme_ctx->tm_attr.mover_tag == "0")
		{
			// default mover
			cme_ctx->tm_attr.mover_tag = "numa_move_all";
		}
		cme_mov = movers_list.at(cme_ctx->tm_attr.mover_tag);
        }
        catch (const std::exception &e)
        {
                CME_ERR("cg_find_mover. Error -> ", e.what ());
                return nullptr;
        }
        return cme_mov;
}

/**
 * @brief function to verify params needed for move commands
 * 	are valid
 * @param command pid, numa node 1, numa node 2
 * @return true if valid params for move
*/
static bool is_valid_cmd_move_param(long app_pid, int n1, int n2)
{
        try
        {
                if (!(pid_exists(app_pid)))
                {
                        CME_ERR("Error in " + string (__FUNCTION__) + " Invalid app pid input");
                        return false;
                }
                if ( (!(is_valid_numa_node(n1))) || (!(is_valid_numa_node(n2))) )
                {
                        CME_ERR("Error in " + string (__FUNCTION__) + " Invalid Numa node input");
                        return false;
                }
        }
        catch (const std::exception &e) 
        {
                CME_ERR("Error -> ", e.what ());
                return false;
        }
        return true;
}

/**
 * @brief function to verify all params needed for move_all
 * 	are present
 * @param command tokens map
 * @return true if valid params for move_all
*/
static bool is_valid_cmd_move_all(cme_global* cg_obj, unordered_map<string, string> &tokens_map)	
{
	try
	{
		if ( (tokens_map.count("src") < 1)
			|| (tokens_map.count("dst") < 1)
			|| (tokens_map.count("app") < 1)
			|| (tokens_map.count("app_pid") < 1)
			|| (tokens_map.count("tm_attr") < 1)
		   )
		{
			throw runtime_error ("Error in " + string (__FUNCTION__) + " :move_all command parameters not found");	
		}
		if (!(!(tokens_map.at("tm_attr").compare("0")) || (cg_obj->movers_list.find(tokens_map.at("tm_attr")) != cg_obj->movers_list.end() ) ))
		{
			throw runtime_error ("Error in " + string (__FUNCTION__) + " :move_all tm_attr param invalid");
		}
                int node_i = stoi (tokens_map.at("src"));
                int node_j = stoi (tokens_map.at("dst"));
                long app_pid = stol (tokens_map.at("app_pid"));
                return is_valid_cmd_move_param(app_pid, node_i, node_j);
	}
        catch (const std::exception &e) 
        {
                CME_ERR("Error -> ", e.what ());
                return false;
        }
}

/**
 * @brief move_all
 * @param command string
 * @return status code of move all, 0 = success
*/
static std::string cg_move_all(cme_global* cg_obj, unordered_map<string, string> &tokens_map)
{
        try
        {
		if (!(is_valid_cmd_move_all(cg_obj, tokens_map)))
                {
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " verify command error ");
                }
                // find cme_context
		cg_obj->cme_contexts_lock();
		cme_context* cme_ctx = cg_obj->cg_find_context(tokens_map, false);
		if (cme_ctx == nullptr)
                {
                        cg_obj->cme_contexts_unlock();
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " cme context not found"); 
                }
                if (cme_ctx->mover_state == CTX_ACTIVE)
                {
                        CME_ERR("cg_move_all. Error -> mover for context busy");
                        cg_obj->cme_contexts_unlock();
                        return std::to_string(-EBUSY);
                }
		// update cme_context
		cme_ctx->mem_attr.src_numa_node = stoi (tokens_map.at("src"));
                cme_ctx->mem_attr.dst_numa_node = stoi (tokens_map.at("dst"));
		cme_ctx->tm_attr.mover_tag = tokens_map.at("tm_attr");
                cme_ctx->operation = "numa_migration";
                cme_ctx->mover_cmd_status = -1;
                cme_ctx->mover_state = CTX_ACTIVE;
                cg_obj->cme_contexts_unlock();
                
		int src = cme_ctx->mem_attr.src_numa_node;
                int dst = cme_ctx->mem_attr.dst_numa_node;
                cme_mover* mover_obj = cg_obj->cg_find_mover(cme_ctx);

                if (mover_obj == nullptr)
		{
			throw runtime_error ("Error in " + string (__FUNCTION__) + " mover not found");
		}
		CME_LOG("INFO", "movername= ", mover_obj->get_name(), " src=", to_string(src), " dst=", to_string(dst));
                std::thread mover_start_th(&cme_mover::move_all, mover_obj, cme_ctx);
                mover_start_th.detach();
        }

        catch (const std::exception &e)
        {
                CME_ERR("cg_move_all. Error -> ", e.what());
                return std::to_string(-EINVAL);
        }
        return to_string (0);
}

/**
 * @brief get_status
 *      For now it is used only for move_all()
 * @param command string
 * @return status code of previous async move command
 * 
*/
static std::string cg_get_status(cme_global* cg_obj, unordered_map<string, string> &tokens_map)
{
        try
        {
		cg_obj->cme_contexts_lock();
                const cme_context* cme_ctx = cg_obj->cg_find_context(tokens_map, true);
		cg_obj->cme_contexts_unlock();
                if (cme_ctx == nullptr)
                {
			throw runtime_error ("Error in " + string (__FUNCTION__) + " Context not found");
                }
		// for now returning status of last completed mover command (move_all)
		// logic will be added later for profiler
		if (cme_ctx->mover_state == CTX_ACTIVE)
		{
			return to_string(-EBUSY);
		}
		CME_LOG("INFO","status = ", to_string(cme_ctx->mover_cmd_status));
		return to_string(cme_ctx->mover_cmd_status);
        }
        catch (const std::exception &e)
        {
                CME_ERR("cg_get_status. Error -> ", e.what ());
                return std::to_string(-EINVAL);
        }
	return std::to_string(-EINVAL);
}

/**
 * @brief get_stats
 * @param command string
 * @return stats string for move command
*/
static std::string cg_get_stats(cme_global* cg_obj, unordered_map<string, string> &tokens_map)
{
        std::string json_stats;
        try
        {
                std::string ret;
                cg_obj->cme_contexts_lock();
                cme_context* cme_ctx = cg_obj->cg_find_context(tokens_map, true);
                if (cme_ctx == nullptr)
                {
			CME_ERR("Context not found");
                        cg_obj->cme_contexts_unlock();
			return std::to_string(-EINVAL);
                }

                cme_mover* mover_obj = cg_obj->cg_find_mover(cme_ctx);
                if (mover_obj == nullptr)
                {
                        cg_obj->cme_contexts_unlock();
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " No mover for context");
                }

                if (cme_ctx->get_stats_state == STATS_INPROGRESS)
                {
                       CME_ERR("cg_get_stats. Error -> get stats for context busy");
                        cg_obj->cme_contexts_unlock();
                        return std::to_string(-EBUSY);
                }

                cme_ctx->get_stats_state = STATS_INPROGRESS;
                cg_obj->cme_contexts_unlock();
                json_stats = mover_obj->get_stats(cme_ctx);
                cg_obj->cme_contexts_lock();
                cme_ctx->get_stats_state = STATS_DONE;
                cg_obj->cme_contexts_unlock();
        }
        catch (const std::exception &e)
        {
                CME_ERR( "cg_get_stats. Error -> ", e.what());
                json_stats = std::to_string(-EINVAL);
        }
        CME_LOG("INFO", "GET_STATS result = ", json_stats);
	return json_stats;
}

/**
 * @brief function to verify all params needed for move
 *      are present
 * @param command tokens map
 * @return true if valid params for move
*/
static bool is_valid_cmd_move(cme_global* cg_obj, unordered_map<string, string> &tokens_map)
{
        try
        {
                if ( (tokens_map.count("slow_tier") < 1)
                        || (tokens_map.count("fast_tier") < 1)
                        || (tokens_map.count("app") < 1)
                        || (tokens_map.count("app_pid") < 1)
                        || (tokens_map.count("tm_attr") < 1)
                   )
                {
			throw runtime_error ("Error in " + string (__FUNCTION__) + " move command parameters not found ");
                }

                int node_i = stoi (tokens_map.at("slow_tier"));
                int node_j = stoi (tokens_map.at("fast_tier"));
                long app_pid = stol (tokens_map.at("app_pid"));
                return is_valid_cmd_move_param(app_pid, node_i, node_j);
        }
        catch (const std::exception &e)
        {
                CME_ERR( "Error -> ", e.what());
                return false;
        }
}


/**
 * @brief move
 * @param command string
 * @return status code of move
*/
static std::string cg_move(cme_global* cg_obj, unordered_map<string, string> &tokens_map)
{
        int ret;
        try
        {
                if (!(is_valid_cmd_move(cg_obj, tokens_map)))
                {
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " verify command error ");
                }

                // find cme_context
                cg_obj->cme_contexts_lock();
                cme_context* cme_ctx = cg_obj->cg_find_context(tokens_map, false);
                if (cme_ctx == nullptr)
                {
                        cg_obj->cme_contexts_unlock();
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " cme context not found");
                }
                if (cme_ctx->mover_state == CTX_ACTIVE)
                {
                        CME_ERR( "cg_move_all. Error -> mover for context busy");
                        cg_obj->cme_contexts_unlock();
                        return std::to_string(-EBUSY);
                }
                // update cme_context
                cme_ctx->mem_attr.slow_tier = stoi (tokens_map.at("slow_tier"));
                cme_ctx->mem_attr.fast_tier = stoi (tokens_map.at("fast_tier"));

                if (!(tokens_map.at("tm_attr").compare("MOVER_AGGRESSIVENESS_LOW")))
                {
                        cme_ctx->tm_attr.ag_level = MOVER_AGGRESSIVENESS_LOW;
                }
                else if (!(tokens_map.at("tm_attr").compare("MOVER_AGGRESSIVENESS_HIGH")))
                {
                        cme_ctx->tm_attr.ag_level = MOVER_AGGRESSIVENESS_HIGH;
                }
                else
                {
                        cg_obj->cme_contexts_unlock();
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " Invalid mover aggressiveness");
                }

                int slow_t = cme_ctx->mem_attr.slow_tier;
                int fast_t = cme_ctx->mem_attr.fast_tier;
                cme_ctx->tm_attr.mover_tag = "mover_damo";

                cme_ctx->mem_attr.src_numa_node = slow_t;
                cme_ctx->mem_attr.dst_numa_node = fast_t;

                cme_mover* mover_obj = cg_obj->cg_find_mover(cme_ctx);
                if (mover_obj == nullptr)
                {
                        cg_obj->cme_contexts_unlock();
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " mover not found");
                }
                CME_LOG("INFO", tokens_map.at("command"), " movername= ", mover_obj->get_name(), " slow_tier=", to_string(slow_t), " fast_tier=", to_string(fast_t));
              
                // Since we are using Damo mover we can use this approach
                // for future movers we can use async thread method similar to move all
                if (!(tokens_map.at("command").compare("move")))
                {
                        cme_ctx->operation = "tier_memory_movement";
                        ret = mover_obj->move(cme_ctx);
                }
                
                else if (!(tokens_map.at("command").compare("move_hot")))
                {
                        cme_ctx->operation = "promote";
                        ret = mover_obj->move_hot(cme_ctx);
                }
                else if (!(tokens_map.at("command").compare("move_cold")))
                {
                        cme_ctx->operation = "demote";
                        // Make faster numa node as the source numa
                        // Make slower numa node as the destination numa 
                        cme_ctx->mem_attr.src_numa_node = fast_t;
                        cme_ctx->mem_attr.dst_numa_node = slow_t;
                        ret = mover_obj->move_cold(cme_ctx);
                }
                else
                {
                        cg_obj->cme_contexts_unlock();
                        return std::to_string(-EINVAL);
                }
                if (!ret)
                {
                        cme_ctx->mover_state = CTX_ACTIVE;
                } 
                cg_obj->cme_contexts_unlock();
        }

        catch (const std::exception &e)
        {
                CME_ERR( "cg_move. Error -> ", e.what());
                return std::to_string(-EINVAL);
        }
        return to_string (ret);
}

/**
 * @brief move_hot
 * @param command string
 * @return status code of move_hot
 *  With damo mover move_hot and move_hot not explicitly implemented
 *  TBD in future for different mover
*/
static std::string cg_move_hot(cme_global* cg_obj, unordered_map<string, string> &tokens_map)
{
        return cg_move(cg_obj, tokens_map);
}

/**
 * @brief move_cold
 * @param command string
 * @return status code of move_cold
 *  With damo mover move_hot and move_cold not explicitly implemented
 *  TBD in future for different mover
*/
static std::string cg_move_cold(cme_global* cg_obj, unordered_map<string, string> &tokens_map)
{
        return cg_move(cg_obj, tokens_map);
}

/**
 * @brief function to verify all params needed for move
 *      are present
 * @param command tokens map
 * @return true if valid params for move
*/
static bool is_valid_cmd_move_stop(cme_global* cg_obj, unordered_map<string, string> &tokens_map)
{
        try
        {
                if ((tokens_map.count("app_pid")  < 1) || (tokens_map.count("app") < 1))
                {
			throw runtime_error ("Error in " + string (__FUNCTION__) + " move stop command parameters not found");
                }
        }
        catch (const std::exception &e)
        {
                CME_ERR( "Error -> ", e.what());
                return false;
        }
        return true;
}

/**
 * @brief move stop
 * @param command string
 * @return status code of move stop
*/
static std::string cg_move_stop(cme_global* cg_obj, unordered_map<string, string> &tokens_map)
{
        int ret;
        try
        {
                if (!(is_valid_cmd_move_stop(cg_obj, tokens_map)))
                {
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " verify command error ");
                }

                std::string app_name = tokens_map.at("app");
                long app_pid = stol(tokens_map.at("app_pid"));
                // find cme_context
                cg_obj->cme_contexts_lock();
                cme_context* cme_ctx = cg_obj->cg_find_context(tokens_map, true);
                if (cme_ctx == nullptr)
                {
                        cg_obj->cme_contexts_unlock();
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " cme context not found");
                }
                cme_mover* mover_obj = cg_obj->cg_find_mover(cme_ctx);
                if (mover_obj == nullptr)
                {
                        CME_ERR( "cg_move_stop. Error -> No mover for context");
                        cg_obj->cme_contexts_unlock();
                        return std::to_string(-EINVAL);
                }
                CME_LOG("INFO", "movername=", mover_obj->get_name(), " app_name=", app_name, " app_pid=", to_string(app_pid));
                if (cme_ctx->mover_state == CTX_ACTIVE)
                {
                        ret = mover_obj->stop(app_name, app_pid);
                        if (ret)
                        {
                                CME_ERR( "cg_move_stop. Error -> stop failed");
                                cg_obj->cme_contexts_unlock();
                                return std::to_string(-EINVAL);
                        }
                }
                delete cme_ctx;
                std::pair<std::string, long> cme_ctx_key = make_pair (app_name, app_pid);
                cg_obj->cme_contexts_list.erase(cme_ctx_key);
                cg_obj->cme_contexts_unlock();
        }
        catch (const std::exception &e)
        {
                CME_ERR( "cg_move_stop. Error -> ", e.what());
                return std::to_string(-EINVAL);
        }
        return to_string (ret);
}

/**
 * @brief cme_command_handler
 * @param command string
 * @return result of command execution functions
*/
std::string cme_global::cme_command_handler(std::string input_cme_command)
{
        std::string result;
        std::string commandValue;
        unordered_map<string, string> command_params_map;
	try
        { 
		// Check and parse valid json command string
                bool cmd_style_json = command_parser_json(input_cme_command, command_params_map);
		if(!cmd_style_json)
		{
			// Older style flat command string
                        command_params_map = token_helper (input_cme_command);
		}
		commandValue = command_params_map.at("command");
		CME_LOG("INFO", "command=", commandValue);
                // Add empty tag by default
                if (command_params_map.count("tag") == 0)
                {
                        command_params_map.try_emplace("tag", "");
                        CME_LOG("INFO", "Add empty tag by default");
                }
        	result = fw_hooks.at (commandValue) (this, command_params_map);
	}
        catch (const std::exception &e)
        {
                CME_ERR( "cme_command_handler. Error -> ", e.what());
                throw runtime_error ("Error in " + string (__FUNCTION__) + "cme_command_handler. Error ->" + e.what());
        }
        return result;
}

/**
 * @brief: Initialize global cme_global object
 * 	Populate map of command name and corresponding function pointers.
 * @return result of command execution functions
*/

int cme_global::initialize()
{
        try
        { 
                fw_hooks.try_emplace("move_all", cg_move_all);
                fw_hooks.try_emplace("get_status", cg_get_status);
                fw_hooks.try_emplace("move", cg_move);
                fw_hooks.try_emplace("move_hot", cg_move_hot);
                fw_hooks.try_emplace("move_cold", cg_move_cold);
                fw_hooks.try_emplace("stop", cg_move_stop);
                fw_hooks.try_emplace("get_stats", cg_get_stats);
        }
        catch (const std::exception &e)
        {
                CME_ERR( "cme global initialize. Error -> ", e.what());
                return (-EINVAL);
        }
        return 0;
}

int cme_global::clean_up()
{
        try
        { 
                CME_LOG("INFO", "Trying to delete global damo config File");
                std::string global_damo_gen_config = CME_CONFIG_PATH + "global_damo_config.yaml";
                filesystem::path filePath(global_damo_gen_config);
                if (filesystem::exists(filePath))
                {
                        CME_LOG("INFO", "Global damo config File exists, deleting");
                        if (remove(global_damo_gen_config.c_str()) == 0)
                        {
                                CME_LOG("INFO", "File: " + global_damo_gen_config + " deleted successfully.");
                        }
                }
                for (auto item : movers_list)
                {
                        delete item.second;
                }
                for (auto item : profilers_list)
                {
                        delete item.second;
                }
        }
        catch (const std::exception &e)
        {
                CME_ERR( "cme clean up. Error -> ", e.what());
                return (-EINVAL);
        }
        return 0;
}
  

