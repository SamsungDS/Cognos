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
#include <chrono>
#include <unistd.h>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/xml_parser.hpp>
#include <filesystem>

#include "include/cme_global.h"

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
      		cout << "reading cme config json = " << conf_filename << endl;
      		pt::read_json (conf_filename, root);

      		profilers_lib = root.get<std::string> ("profilers_lib_path");
      		movers_lib = root.get<std::string> ("movers_lib_path");
      		cout << profilers_lib << " -- " << movers_lib << endl;
    	}
  	catch (const std::exception &e)
    	{
      		std::cerr << "Unable to read cme config json. Error -> " << e.what ()
                	<< '\n';
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
                cout << "cme discovery in path = " << feat_sm_svcs_dir << endl;
                DIR *dirfp = opendir(feat_sm_svcs_dir.c_str());

                if (dirfp == nullptr)
                {
                        cout << "Invalid feature service directory" << endl;
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
                        	cout << "No Service found" << endl;
                        	continue;
                        }

                        std::string feature_lib_str = feat_sm_svcs_dir + "/" + entry_name;
                        void *handle = dlopen(feature_lib_str.c_str(), RTLD_LAZY);
                        if (!handle)
                        {
                                cerr << "Failed to load library " << feature_lib_str << " Reason: " << dlerror() << endl;
                                continue;
                        }

                        if (type == CME_MOVER)
                        {
                                auto register_cme_fn = reinterpret_cast<cme_mover* (*)()>(dlsym(handle, "register_cme_fn"));
                                if (!register_cme_fn) {
                                        cerr << "Cannot load symbols from library " << feature_lib_str << " Reason: " << dlerror() << endl;
                                        dlclose(handle);
                                        return 1;
                                }
                                cme_mover* cme_obj = register_cme_fn();
                                if (!cme_obj) {
                                        cerr << "Object creation failed" << endl;
                                        dlclose(handle);
                                        continue;
                                }
				mover_register(cme_obj->get_name(), cme_obj);
                        }
                        else if (type == CME_PROFILER)
                        {
                                
                                auto register_cme_fn = reinterpret_cast<cme_profiler* (*)()>(dlsym(handle, "register_cme_fn"));
                                if (!register_cme_fn) {
                                        cerr << "Cannot load symbols from library " << feature_lib_str << " Reason: " << dlerror() << endl;
                                        dlclose(handle);
                                        return 1;
                                }
                                cme_profiler* cme_obj = register_cme_fn();
                                if (!cme_obj) {
                                        cerr << "Object creation failed" << endl;
                                        dlclose(handle);
                                        continue;
                                }
                                profilers_list.try_emplace(cme_obj->get_name(), cme_obj);
				profiler_register(cme_obj->get_name(), cme_obj);
                        }
                        else
                        {
                                throw runtime_error ("Error in " + string (__FUNCTION__) + "Invalid CME type");
                        }
                }
        }

        catch (const std::exception &e)
        {
                std::cerr << "Error in cme discovery: Error -> " << e.what () << endl;
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
        int rc1,rc2;
        try
        {
                rc1 = _cme_discovery(movers_lib, CME_MOVER);
                if (rc1 !=0)
                {
                        throw runtime_error ("Error in " + string (__FUNCTION__) + "cme_discovery failed for : " + movers_lib);
                }
                rc2 = _cme_discovery(profilers_lib, CME_PROFILER);
                if (rc2 !=0)
                {
                         std::cerr << "Error in " + string (__FUNCTION__) + "cme_discovery failed for : " + profilers_lib << std::endl;
                }
        }
        catch (const std::exception &e)
        {
          std::cerr << "cme_discovery. Error -> " << e.what ()
                    << '\n';
                    return -EINVAL;
        }

	std::cout << "Profilers discovered count = " << profilers_list.size() << std::endl;
	std::cout << "Movers discovered count = " << movers_list.size() << std::endl;
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
                        cout << "cme context found for key:"  << cme_ctx_key.first << "_" << to_string(cme_ctx_key.second) <<endl;
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
                return cme_ctx;
        }
        catch (const std::exception &e)
        {
          std::cerr << "cg_find_context. Error -> " << e.what () << endl;
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
                std::cerr << "cg_find_mover. Error -> " << e.what () << endl;
                return nullptr;
        }
        return cme_mov;
}

/**
 * @brief call back function for move_all
 *      This function canimplement diffrent actions to be done
 *      at the end on the move_all thread function like updating
 *      the corresponding CME context.
 * @param  cb_ctx: corresponding cme_context
 * @return None
*/
void callback_fn_move_all(void* cb_ctx, int status)
{
        std::cout << "Callback function callback_fn_move_all started"  << std::endl;
        cme_context* ctx = (cme_context*) cb_ctx;
        ctx->mover_cmd_status = status;
        ctx->mover_state = CTX_INACTIVE;
        cout << "Callback function callback_fn_move_all finished; updated context state=" << to_string(ctx->mover_state) << endl;
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
				
	}
        catch (const std::exception &e) 
        {
                std::cerr << "Error -> " << e.what () << endl;
                return false;
        }
        return true;
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
		long app_pid = stol(tokens_map.at("app_pid"));
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
                        std::cerr << "cg_move_all. Error -> mover for context busy" << endl;
                        cg_obj->cme_contexts_unlock();
                        return std::to_string(-EBUSY);
                }
		// update cme_context
		cme_ctx->mem_attr.src_numa_node = stoi (tokens_map.at("src"));
                cme_ctx->mem_attr.dst_numa_node = stoi (tokens_map.at("dst"));
		cme_ctx->tm_attr.mover_tag = tokens_map.at("tm_attr");
                cme_ctx->mover_state = CTX_ACTIVE;
                cg_obj->cme_contexts_unlock();
                
		int src = cme_ctx->mem_attr.src_numa_node;
                int dst = cme_ctx->mem_attr.dst_numa_node;
                cme_ctx->mover_obj = cg_obj->cg_find_mover(cme_ctx);
                if (cme_ctx->mover_obj == nullptr)
		{
			throw runtime_error ("Error in " + string (__FUNCTION__) + " mover not found");
		}
		cout << "movername= " << cme_ctx->mover_obj->get_name() << " src=" << to_string(src) << " dst="<< to_string(dst) << endl;               
		// Create detached thread for move_all function
                std::thread mover_start_th(&cme_mover::move_all, cme_ctx->mover_obj , app_pid, src, dst, callback_fn_move_all  ,(void*)cme_ctx, 0);
                mover_start_th.detach();;
        }

        catch (const std::exception &e)
        {
                std::cerr << "cg_move_all. Error -> " << e.what () << endl;
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
		cout << "status = " << to_string(cme_ctx->mover_cmd_status) << endl;
		return to_string(cme_ctx->mover_cmd_status);
        }
        catch (const std::exception &e)
        {
                std::cerr << "cg_get_status. Error -> " << e.what () << endl;
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
        std::string ret;
        try
        {
                std::string app_name = tokens_map.at("app");
		long app_pid = stol(tokens_map.at("app_pid"));
                cg_obj->cme_contexts_lock();
                cme_context* cme_ctx = cg_obj->cg_find_context(tokens_map, true);
                if (cme_ctx == nullptr)
                {
			std::cerr << "Context not found" << endl;
                        cg_obj->cme_contexts_unlock();
			return std::to_string(-EINVAL);
                }

                if ((cme_ctx->tm_attr.mover_tag).compare("mover_damo"))
                {
                        cg_obj->cme_contexts_unlock();
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " No valid prior mover for context");
                }
                cme_ctx->mover_obj = cg_obj->cg_find_mover(cme_ctx);
                if (cme_ctx->mover_obj == nullptr)
                {
                        cg_obj->cme_contexts_unlock();
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " No mover for context");
                }

                if (cme_ctx->get_stats_state == STATS_INPROGRESS)
                {
                        std::cerr << "cg_get_stats. Error -> get stats for context busy" << endl;
                        cg_obj->cme_contexts_unlock();
                        return std::to_string(-EBUSY);
                }

                cme_ctx->get_stats_state = STATS_INPROGRESS;
                cg_obj->cme_contexts_unlock();
                ret = cme_ctx->mover_obj->get_stats(app_name, app_pid);
                cg_obj->cme_contexts_lock();
                cme_ctx->get_stats_state = STATS_DONE;
                cg_obj->cme_contexts_unlock();
        }
        catch (const std::exception &e)
        {
                std::cerr << "cg_get_stats. Error -> " << e.what () << endl;
                ret = std::to_string(-EINVAL);
        }
	return ret;
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
        }
        catch (const std::exception &e)
        {
                std::cerr << "Error -> " << e.what () << endl;
                return false;
        }
        return true;
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
                        std::cerr << "cg_move_all. Error -> mover for context busy" << endl;
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
                cme_ctx->mover_obj = cg_obj->cg_find_mover(cme_ctx);
                if (cme_ctx->mover_obj == nullptr)
                {
                        cg_obj->cme_contexts_unlock();
                        throw runtime_error ("Error in " + string (__FUNCTION__) + " mover not found");
                }
                cout << tokens_map.at("command") << " movername= " << cme_ctx->mover_obj->get_name() << " slow_tier=" << to_string(slow_t) << " fast_tier="<< to_string(fast_t) << endl;
                std::string app_name = tokens_map.at("app");
                long app_pid = stol(tokens_map.at("app_pid"));
                
                // Since we are using Damo mover we can use this approach
                // for future movers we can use async thread method similar to move all

                if (!(tokens_map.at("command").compare("move")))
                {
                        ret = cme_ctx->mover_obj->move(app_name, app_pid, slow_t, fast_t, cme_ctx->tm_attr.ag_level);
                }
                
                else if (!(tokens_map.at("command").compare("move_hot")))
                {
                        ret = cme_ctx->mover_obj->move_hot(app_name, app_pid, slow_t, fast_t, cme_ctx->tm_attr.ag_level);
                }
                else if (!(tokens_map.at("command").compare("move_cold")))
                {
                        ret = cme_ctx->mover_obj->move_cold(app_name, app_pid, slow_t, fast_t, cme_ctx->tm_attr.ag_level);
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
                std::cerr << "cg_move. Error -> " << e.what () << endl;
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
                std::cerr << "Error -> " << e.what () << endl;
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
                cme_ctx->mover_obj = cg_obj->cg_find_mover(cme_ctx);
                if (cme_ctx->mover_obj == nullptr)
                {
                        std::cerr << "cg_move_stop. Error -> No mover for context" << endl;
                        cg_obj->cme_contexts_unlock();
                        return std::to_string(-EINVAL);
                }
                cout << "movername=" << cme_ctx->mover_obj->get_name() << " app_name=" << app_name << " app_pid="<< to_string(app_pid) << endl;
                if (cme_ctx->mover_state == CTX_ACTIVE)
                {
                        ret = cme_ctx->mover_obj->stop(app_name, app_pid);
                        if (ret)
                        {
                                std::cerr << "cg_move_stop. Error -> stop failed" << endl;
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
                std::cerr << "cg_move_stop. Error -> " << e.what () << endl;
                return std::to_string(-EINVAL);
        }
        return to_string (ret);
}

/**
 * @brief StartTuning
 * @param command string
 * @return status code of StartTuning
 *  StartTuning redirects to move 
*/
static std::string cg_StartTuning(cme_global* cg_obj, unordered_map<string, string> &tokens_map)
{
        try
        {
                tokens_map.try_emplace("app", tokens_map.at("application"));
                tokens_map.try_emplace("fast_tier", tokens_map.at("dram_node"));
                tokens_map.try_emplace("app_pid", tokens_map.at("application_id"));
                tokens_map.try_emplace("slow_tier", tokens_map.at("cxl_node"));
                tokens_map.try_emplace("tm_attr", "MOVER_AGGRESSIVENESS_LOW");
                tokens_map["command"] = "move";
                return cg_move(cg_obj, tokens_map);
                
        }
        catch(const std::exception& e)
        {
                std::cerr << "StartTuning. Error -> " << e.what () << endl;
                return std::to_string(-EINVAL);
        }
}

/**
 * @brief StopTuning
 * @param command string
 * @return status code of StopTuning
 *  StopTuning redirects to move
*/
static std::string cg_StopTuning(cme_global* cg_obj, unordered_map<string, string> &tokens_map)
{
        try
        {
                tokens_map.try_emplace("app", tokens_map.at("application"));
                tokens_map.try_emplace("app_pid", tokens_map.at("application_id"));
                return cg_move_stop(cg_obj, tokens_map);
        }
        catch(const std::exception& e)
        {
                std::cerr << "cg_StopTuning. Error -> " << e.what () << endl;
                return std::to_string(-EINVAL);
        }
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
		cout << "command=" << commandValue << endl;
        	result = fw_hooks.at (commandValue) (this, command_params_map);
	}
        catch (const std::exception &e)
        {
                std::cerr << "cme_command_handler. Error -> " << e.what () << endl;
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
                fw_hooks.try_emplace("StartTuning", cg_StartTuning);
                fw_hooks.try_emplace("StopTuning", cg_StopTuning);
                fw_hooks.try_emplace("get_stats", cg_get_stats);

        }
        catch (const std::exception &e)
        {
                std::cerr << "cme global initialize. Error -> " << e.what () << endl;
                return (-EINVAL);
        }
        return 0;
}

int cme_global::clean_up()
{
        try
        { 
                std::string global_damo_gen_config = CME_CONFIG_PATH + "global_damo_config.yaml";
                filesystem::path filePath(global_damo_gen_config);
                if (filesystem::exists(filePath))
                {
                        cout << "Global damo config File exists, deleting.\n";
                        if (remove(global_damo_gen_config.c_str()) == 0)
                        {
                                cout << "File: " + global_damo_gen_config + " deleted successfully." << endl;
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
                std::cerr << "cme clean up. Error -> " << e.what () << endl;
                return (-EINVAL);
        }
        return 0;
}
  

