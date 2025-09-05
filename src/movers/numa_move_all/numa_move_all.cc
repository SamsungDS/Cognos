
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <numa.h>
#include <numaif.h>
#include <stdexcept>
#include <thread>
#include <chrono>
#include <sstream>
#include <functional>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/xml_parser.hpp>

#include "numa_move_all.h"
#include "cme_utils.h"
#include "cme_context.h"

using namespace std;

/**
 * @brief call back/post operation function for move_all
 *      This function canimplement diffrent actions to be done
 *      at the end on the move_all thread function like updating
 *      the corresponding CME context.
 * @param  cb_ctx: corresponding cme_context
 * @return None
*/
static int post_fn_move_all(cme_context* cme_ctx, int status)
{   
        cout << "Callback function callback_fn_move_all started"  << std::endl;
        cme_ctx->mover_cmd_status = status;
        cme_ctx->mover_state = CTX_INACTIVE;
        cout << "Callback function callback_fn_move_all finished; updated context state=" << to_string(cme_ctx->mover_state) << endl;
        return 0;
}

/**
 * @brief helper function  for stats processing for numa migration

 * @param  stats string from numa_move_all mover and reference to output string components
 * @return None
*/
static void process_stats_string(std::string_view str, std::string& key, std::string& numberPart, std::string& unitPart)
{
        auto op_str =  std::string(str);
        size_t colonPos = op_str.find(':');
        // Extract the key part
        key = op_str.substr(0, colonPos);
        // Extract the number and unit part after the colon
        std::string numberAndUnit = op_str.substr(colonPos + 1);
        size_t pos = numberAndUnit.find_first_not_of("0123456789.");
        if (pos == std::string::npos) {
                // If no non-numeric character is found, the entire part is numeric
                numberPart = numberAndUnit;
                unitPart = ""; // No unit part
        } else {
                // Extract the numeric part
                numberPart = numberAndUnit.substr(0, pos);
                // Extract the unit part
                unitPart = numberAndUnit.substr(pos);
        }
}

/**
 * @brief pre operation function for move_all
 *      This function can implement diffrent actions to be done
 *      before the move_all thread function like updating
 *      the corresponding CME context with initial memory footprints
 * @param  cb_ctx: corresponding cme_context
 * @return None
*/
static int pre_fn_move_all(cme_context* cme_ctx, const std::string& stats_string)
{
        try
        {
                std::cout << "pre_fn_move_all started : statsstring = "  << stats_string << std::endl;
                //parse and update stats
                std::istringstream stream(stats_string);
                std::string data;
                bool src_done = false;
                bool dst_done = false;
                while (stream >> data)
                {
                        if (src_done && dst_done)
                        {
                                break;
                        }
                        std::string key;
                        std::string numberPart;
                        std::string unitPart;
                        process_stats_string(data, key, numberPart, unitPart);

                        if (stoi(key) == cme_ctx->mem_attr.src_numa_node)
                        {
                                cme_ctx->mem_attr.src_numa_start_usage = stod(numberPart);
                                cme_ctx->mem_attr.usage_unit = unitPart;
                                src_done = true;
                        }
                        if (stoi(key) == cme_ctx->mem_attr.dst_numa_node)
                        {
                                cme_ctx->mem_attr.dst_numa_start_usage = stod(numberPart);
                                dst_done = true;
                        }
                }
                cout << "pre_fn_move_all finished; updated src_numa_start_usage: " << cme_ctx->mem_attr.src_numa_start_usage << " dst_numa_start_usage: " <<  cme_ctx->mem_attr.dst_numa_start_usage << endl;
        }
        catch (const std::exception &e) 
        {
                std::cerr << "Error -> " << e.what () << endl;
                cme_ctx->mover_cmd_status = -errno;
                cme_ctx->mover_state = CTX_INACTIVE;
                return -errno;
        }
        return 0;
}

static std::string process_numastat(long app_pid)
{
        std::string result;
        if (pid_exists(app_pid))
        {
                string cmd;
                vector<string> cmd_output;
                cmd = "numastat -p " + to_string(app_pid) +  + " 2>&1";
                if (auto ret = execute_command(cmd, cmd_output, false); ret !=0)
                {
                        throw runtime_error("error in executing command: " + cmd);
                }
                std::istringstream val_stream(cmd_output[cmd_output.size()-1]);
                string value;
                int i = 0;
                while (val_stream >> value)
                {
                        if(value != "Total")
                        {
                                result = result + to_string(i) + ":" + value + "MB ";
                                i++;
                        }
                }
                result = result.substr(0, result.length() - 1);
        }
        return result;
}

static int _numa_move_all(long target_pid, unsigned int node_src, unsigned int node_dest)
{
        cout << "Started " <<  string (__FUNCTION__) << "--"<< target_pid << "--" << node_src << "--" <<node_dest <<endl;
	int ret = 0;
        try
        {
                unsigned int numa_count_conf = numa_num_configured_nodes();
                unsigned int numa_count_possible = numa_num_possible_nodes();

                if( node_src < 0  || node_src >= numa_count_conf || node_dest < 0 || node_dest >= numa_count_conf)
                {
			std::cerr << "Error in " + string(__FUNCTION__) + " invalid NUMA node input" << endl;
			return -EINVAL;
                }

                struct bitmask *src_nodes = numa_bitmask_alloc(numa_count_possible);
                struct bitmask *dst_nodes = numa_bitmask_alloc(numa_count_possible);
                
                numa_bitmask_setbit(src_nodes, node_src);
                numa_bitmask_setbit(dst_nodes, node_dest);

                cout << "starting numa migrate pages from node = " << node_src << " to node = " << node_dest << endl;
                int pid  = static_cast<int>(target_pid);
		ret = numa_migrate_pages(pid, src_nodes, dst_nodes);
                if (ret == 0)
                {
                        cout << "All pages moved" << endl;
                }
                else
                {
		cout << "numa_migrate_pages return val = " << ret << " Error = " << to_string(errno) << " : " << strerror(errno) << endl;
			return -errno;
                }
        }
        catch(const std::exception& e)
        {
                std::cerr << e.what() << '\n';
		return -errno;
	}

	return ret;
}

extern "C" cme_mover* register_cme_fn() {

                cout << "Registering cme_mover numa_move_all " + string (__FUNCTION__) << endl;
                return new numa_move_all(std::string("numa_move_all"));

}

extern "C" void unregister_cme_fn(cme_mover* mover_obj) {

        cout << "Unregistering cme mover numa_move_all " + string (__FUNCTION__) << endl;
        delete mover_obj;
}

int numa_move_all::move_all(cme_context* ctx)
{
        try
        {
                cout << "moveall try: "<< endl;
                cout << name << " Started  " <<  string (__FUNCTION__) <<  "--"<< ctx->app_attr.app_pid << "--" << ctx->mem_attr.src_numa_node << "--" <<  ctx->mem_attr.dst_numa_node << endl;
                if (ctx->app_attr.app_pid == DUMMY_PID)
                {        
                        move_hot(DUMMY_PROCESS, DUMMY_PID, 1, 0, MOVER_AGGRESSIVENESS_LOW);
                        move_cold(DUMMY_PROCESS, DUMMY_PID, 1, 0, MOVER_AGGRESSIVENESS_LOW);
                        move(DUMMY_PROCESS, DUMMY_PID, 1, 0, MOVER_AGGRESSIVENESS_LOW);
                        get_status();
                        stop(DUMMY_PROCESS, DUMMY_PID);
                        return 0;
                }
                int ret;
                
                cout << "threadid=" << std::this_thread::get_id() << endl;
                std::string stats = process_numastat(ctx->app_attr.app_pid);
                cout << "initial stats=" << stats << endl;

                int chk = pre_fn_move_all(ctx, stats);
                if (chk)
                {
                        std::cerr <<"Initial stats get failed" << std::endl;
                        return chk;
                }
                ret = _numa_move_all(ctx->app_attr.app_pid, ctx->mem_attr.src_numa_node , ctx->mem_attr.dst_numa_node);
                cout << name << " Finished  " <<  string (__FUNCTION__) << "--"<< ctx->app_attr.app_pid << "--" << ctx->mem_attr.src_numa_node << "--" <<  ctx->mem_attr.dst_numa_node << " ret = " << ret <<endl;
                post_fn_move_all(ctx, ret);
        }
        catch(const std::exception& e)
        {
                std::cerr << e.what() << '\n';
                return -errno;
        }
        return 0;
}

int numa_move_all::move_hot(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}

int numa_move_all::move_cold(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}

int numa_move_all::move(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}

int numa_move_all::get_status()
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}

std::string numa_move_all::get_stats(cme_context* cme_ctx)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        std::string json_string_ret;
        try
        {
                std::string result = process_numastat(cme_ctx->app_attr.app_pid);
                std::stringstream json_stream;
                namespace pt = boost::property_tree;
                pt::ptree root;
                pt::ptree child_node;
                std::istringstream stream(result);
                std::string data;
                std::string usage_unit; 
                double src_current_usage = 0.0;
                double dst_current_usage = 0.0; 
                double percent_moved = 0.0;
                bool src_done = false;
                bool dst_done = false;
                while (stream >> data)
                {
                        if (src_done && dst_done)
                        {
                                break;
                        }
                        std::string key;
                        std::string numberPart;
                        std::string unitPart;
                        process_stats_string(data, key, numberPart, unitPart);

                        if (stoi(key) == cme_ctx->mem_attr.src_numa_node)
                        {
                                src_current_usage = stod(numberPart);
                                usage_unit = unitPart;
                                src_done = true;
                        }
                        if (stoi(key) == cme_ctx->mem_attr.dst_numa_node)
                        {
                                dst_current_usage = stod(numberPart);
                                dst_done = true;
                        }
                }
                percent_moved = ((cme_ctx->mem_attr.src_numa_start_usage - src_current_usage) / (cme_ctx->mem_attr.src_numa_start_usage)) * 100.00;

                child_node.put("operation", cme_ctx->operation);
                child_node.put("app_context:", cme_ctx->app_attr.app_name + "_" + to_string(cme_ctx->app_attr.app_pid));
                child_node.put("src_numa_node", cme_ctx->mem_attr.src_numa_node);
                child_node.put("dst_numa_node", cme_ctx->mem_attr.dst_numa_node);
                child_node.put("src_numa_start_usage", to_string(cme_ctx->mem_attr.src_numa_start_usage) + cme_ctx->mem_attr.usage_unit);
                child_node.put("dst_numa_start_usage", to_string(cme_ctx->mem_attr.dst_numa_start_usage) + cme_ctx->mem_attr.usage_unit);
                child_node.put("src_numa_current_usage", to_string(src_current_usage) + usage_unit);
                child_node.put("dst_numa_current_usage", to_string(dst_current_usage) + usage_unit);
                child_node.put("%_moved", percent_moved);
                root.add_child("observations", child_node);
                pt::write_json(json_stream, root);
                json_string_ret = json_stream.str(); 
        }

        catch(const std::exception& e)
        {
                std::cerr << "Error in " + string(__FUNCTION__) + " : " + e.what() << endl;
                return std::string();
        }
        return json_string_ret;
}

int numa_move_all::stop(string app_name, long app_pid)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}

numa_move_all::numa_move_all (string _name)
{
  name = _name;
}

std::string numa_move_all::get_name()
{
        return name;
}
