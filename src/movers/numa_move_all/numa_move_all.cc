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
#include <memory>
#include <sstream>
#include <functional>
#include <nlohmann/json.hpp>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/xml_parser.hpp>
#include "numa_move_all.h"
#include "cme_utils.h"
#include "cme_context.h"
#include "cme_publisher.h"
#include "cme_logger.h"

using namespace std;

/**
 * @brief Function for start event for migration operation.
 * Implements numa migration start event.
 * @param  cme_ctx: corresponding cme_context
 * @return None
*/
static void generate_start_migraion_event(cme_context* cme_ctx)
{
        CME_ENTRY();
        struct cme_event event_obj;
        nlohmann::json event_data;
        std::string app_ctx_id = cme_ctx->app_attr.app_name + "_" + to_string(cme_ctx->app_attr.app_pid);
        event_data["operation"] = cme_ctx->operation;
        event_data["src_numa_node"] = cme_ctx->mem_attr.src_numa_node;
        event_data["dst_numa_node"] = cme_ctx->mem_attr.dst_numa_node;
        std::string status_string = (cme_ctx->mover_cmd_status == 0) ? "success: " : "failure: ";
        status_string += to_string(cme_ctx->mover_cmd_status) + ":" + strerror(-(cme_ctx->mover_cmd_status));
        event_data["status"] = status_string;
        event_data["name"] = "numa_migration_start";
        event_obj.event_json["timestamp"] = getCurrentTimestamp();
        event_obj.event_json["source"] = app_ctx_id;
        event_obj.event_json["msg"] = "numa migration operation started";
        event_obj.event_json["observations"] = event_data;
        
        int ret = publish_cme_event(event_obj);
        if (ret)
        {
                CME_ERR("Failed to publish CME event, return = ", to_string(ret));
        }
        else
        {
                CME_LOG("INFO", "Published CME event successful");
        }
        CME_EXIT();
}

/**
 * @brief Function for post numa miration operation.
 * Implements numa migration completion event.
 * @param  cme_ctx: corresponding cme_context
 * @return None
*/
static void post_fn_move_all(cme_context* cme_ctx)
{   
        CME_ENTRY();
        //Generate completion event
        struct cme_event event_obj;
        std::string app_ctx_id = cme_ctx->app_attr.app_name + "_" + to_string(cme_ctx->app_attr.app_pid);
        nlohmann::json event_data;
        std::string status_string = (cme_ctx->mover_cmd_status == 0) ? "success: " : "failure: ";
        status_string += to_string(cme_ctx->mover_cmd_status) + ":" + strerror(-(cme_ctx->mover_cmd_status));
        event_data["operation"] = cme_ctx->operation;
        event_data["src_numa_node"] = cme_ctx->mem_attr.src_numa_node;
        event_data["dst_numa_node"] = cme_ctx->mem_attr.dst_numa_node;
        event_data["status"] = status_string;
        event_data["name"] = "numa_migration_completion";
        event_obj.event_json["observations"] = event_data;
        event_obj.event_json["msg"] = "numa migration operation completed";
        event_obj.event_json["timestamp"] = getCurrentTimestamp();
        event_obj.event_json["source"] = app_ctx_id;
        int ret = publish_cme_event(event_obj);
        if (ret)
        {
                CME_ERR("Failed to publish CME event, return = ", to_string(ret));
        }
        else
        {
                CME_LOG("INFO", "Published CME event successful");
        }
        CME_EXIT();
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
                CME_ENTRY();
                CME_LOG("INFO", "statsstring = ", stats_string);
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
                CME_LOG("INFO", "pre_fn_move_all finished; updated src_numa_start_usage: ", to_string(cme_ctx->mem_attr.src_numa_start_usage), " dst_numa_start_usage: ", to_string(cme_ctx->mem_attr.dst_numa_start_usage));
        }
        catch (const std::exception &e) 
        {
                CME_ERR("Error -> ",  e.what ());
                return -EINVAL;
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
	CME_ENTRY();
        int ret = 0;
        try
        {
                unsigned int numa_count_conf = numa_num_configured_nodes();
                unsigned int numa_count_possible = numa_num_possible_nodes();

                if( node_src < 0  || node_src >= numa_count_conf || node_dest < 0 || node_dest >= numa_count_conf)
                {
                        CME_ERR("Error in " + string(__FUNCTION__) + " invalid NUMA node input");
			return -EINVAL;
                }

                struct bitmask *src_nodes = numa_bitmask_alloc(numa_count_possible);
                struct bitmask *dst_nodes = numa_bitmask_alloc(numa_count_possible);
                
                numa_bitmask_setbit(src_nodes, node_src);
                numa_bitmask_setbit(dst_nodes, node_dest);

                CME_LOG("INFO", "starting numa migrate pages from node = ", to_string(node_src), " to node = ", to_string(node_dest)) ;
                int pid  = static_cast<int>(target_pid);
		ret = numa_migrate_pages(pid, src_nodes, dst_nodes);
                if (ret == 0)
                {
                        CME_LOG("INFO", "All pages moved");
                }
                else
                {
                        CME_ERR("numa_migrate_pages return val = ", to_string(ret), " Error = ", to_string(errno), " : ", strerror(errno));
			return -errno;
                }
        }
        catch(const std::exception& e)
        {
                CME_ERR(e.what());
		return -errno;
	}
	return ret;
}

extern "C" cme_mover* register_cme_fn() {

                CME_LOG("INFO","Registering cme_mover numa_move_all " + string (__FUNCTION__));
                return new numa_move_all(std::string("numa_move_all"));

}

extern "C" void unregister_cme_fn(cme_mover* mover_obj) {

        CME_LOG("INFO","Unregistering cme mover numa_move_all " + string (__FUNCTION__));
        delete mover_obj;
}

int numa_move_all::move_all(cme_context* ctx)
{
        try
        {
                CME_ENTRY();
                CME_LOG("INFO", "--" , to_string(ctx->app_attr.app_pid) , "--" , to_string(ctx->mem_attr.src_numa_node) , "--" , to_string(ctx->mem_attr.dst_numa_node));
                if (ctx->app_attr.app_pid == DUMMY_PID)
                {        
                        move_hot(DUMMY_PROCESS, DUMMY_PID, 1, 0, MOVER_AGGRESSIVENESS_LOW);
                        move_cold(DUMMY_PROCESS, DUMMY_PID, 1, 0, MOVER_AGGRESSIVENESS_LOW);
                        move(DUMMY_PROCESS, DUMMY_PID, 1, 0, MOVER_AGGRESSIVENESS_LOW);
                        get_status();
                        stop(DUMMY_PROCESS, DUMMY_PID);
                        return 0;
                }
                CME_LOG("INFO", "threadid=",std::this_thread::get_id());
                std::string stats = process_numastat(ctx->app_attr.app_pid);
                ctx->mover_cmd_status = pre_fn_move_all(ctx, stats);
                generate_start_migraion_event(ctx);
                if (ctx->mover_cmd_status)
                {
                        throw runtime_error("Error in " + string(__FUNCTION__) + "pre processing error");
                }
                ctx->mover_cmd_status = -1;
                ctx->mover_cmd_status = _numa_move_all(ctx->app_attr.app_pid, ctx->mem_attr.src_numa_node , ctx->mem_attr.dst_numa_node);
                CME_LOG("INFO", name, " Finished  ",  string (__FUNCTION__) , "--", ctx->app_attr.app_pid, "--" , ctx->mem_attr.src_numa_node, "--",  ctx->mem_attr.dst_numa_node, " return = ", ctx->mover_cmd_status);
                post_fn_move_all(ctx);
        }
        catch(const std::exception& e)
        {
                CME_ERR(e.what());
        }
        ctx->mover_state = CTX_INACTIVE;
        return 0;
}

int numa_move_all::move_hot(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level)
{
        CME_ENTRY();
        return 0;
}

int numa_move_all::move_cold(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level)
{
        CME_ENTRY();
        return 0;
}

int numa_move_all::move(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level)
{
        CME_ENTRY();
        return 0;
}

int numa_move_all::get_status()
{
        CME_ENTRY();
        return 0;
}

std::string numa_move_all::get_stats(cme_context* cme_ctx)
{
        CME_ENTRY();
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
                CME_ERR("Error in " , string(__FUNCTION__) , " : ", e.what());
                return std::string();
        }
        return json_string_ret;
}

int numa_move_all::stop(string app_name, long app_pid)
{
        CME_ENTRY();
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
