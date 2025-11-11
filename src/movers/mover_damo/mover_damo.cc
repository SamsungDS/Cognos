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
#include <cstdlib>

#include "mover_damo.h"
#include "damo_main.h"
#include "cme_utils.h"
#include "cme_logger.h"
#include "cme_publisher.h"

using namespace std;


/**
 * @brief Function for start event for auto tier data movement operation.
 * Implements auto tier data movement start event.
 * @param  cme_ctx: corresponding cme_context
 * @return None
*/
static void generate_start_data_movement_event(cme_context* cme_ctx, int damo_start_ret)
{
        CME_ENTRY();
        struct cme_event event_obj;
        nlohmann::json event_data;
        std::string app_ctx_id = cme_ctx->app_attr.app_name + "_" + to_string(cme_ctx->app_attr.app_pid);
        event_data["operation"] = cme_ctx->operation;
        event_data["slow_tier"] = cme_ctx->mem_attr.slow_tier;
        event_data["fast_tier"] = cme_ctx->mem_attr.fast_tier;
        std::string status_string = (damo_start_ret == 0) ? "success: " : "failure: ";
        status_string += to_string(damo_start_ret) + ":" + strerror(abs(damo_start_ret));
        event_data["status"] = status_string;
        event_data["name"] = "tm_data_movement_started";
        event_obj.event_json["timestamp"] = getCurrentTimestamp();
        event_obj.event_json["source"] = app_ctx_id;
        event_obj.event_json["msg"] = "tiered memory data movement operation started";
        event_obj.event_json["observations"] = event_data;
        event_obj.event_json["tag"] = cme_ctx->event_tag;

        if (int ret = publish_cme_event(event_obj);ret)
        {
                CME_ERR("Failed to publish CME event, return = ", to_string(ret));
        }
        else
        {
                CME_LOG("INFO", "Published CME event successful");
        }
        CME_EXIT();
}

int start_damo_main(cme_context* ctx, int move_select)
{
        int ret;
        try
        {
                ret = start(ctx->app_attr.app_name, ctx->app_attr.app_pid, ctx->mem_attr.slow_tier, ctx->mem_attr.fast_tier, ctx->tm_attr.ag_level, move_select);
                generate_start_data_movement_event(ctx, ret);
        }
        catch (const std::exception& e)
        {
                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : " + string(e.what()));
                ret = -EINVAL;
        }
        CME_LOG("INFO", "Error in ret = " + to_string(ret));
        return ret;
}

int stop_damo_main(string app_name, long app_pid)
{
        int ret;
        try
        {
                ret = stop(app_name, app_pid);
        }
        catch (const std::exception& e)
        {
                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : " + string(e.what()));
                ret = -EINVAL;
        }
        return ret;
}

std::string stats_damo_main(cme_context *ctx)
{
        std::string json_stats;
        try
        {
                std::string ret;
                ret = get_stats(ctx->app_attr.app_name, ctx->app_attr.app_pid);
                std::stringstream json_stream;
                namespace pt = boost::property_tree;
                pt::ptree root;
                pt::ptree child_node;
                child_node.put("operation", ctx->operation);
                child_node.put("app_context:", ctx->app_attr.app_name + "_ " + to_string(ctx->app_attr.app_pid));
                child_node.put("memory_movement_stats", ret);
                root.add_child("observations", child_node);
                pt::write_json(json_stream, root);
                json_stats = json_stream.str();
        }
        catch (const std::exception& e)
        {
                CME_LOG("INFO", "Error in " + string(__FUNCTION__) + " : " + string(e.what()));
                json_stats = to_string(-EINVAL);
        }
        return json_stats;
}

extern "C" cme_mover* register_cme_fn() {

                CME_LOG("INFO", "Registering cme_mover mover_damo " + string (__FUNCTION__));
                return new mover_damo(std::string("mover_damo"));

}

extern "C" void unregister_cme_fn(cme_mover* mover_obj) {

        CME_LOG("INFO", "Unregistering cme mover mover_damo " + string (__FUNCTION__));
        delete mover_obj;

}

int mover_damo::move_all(cme_context* ctx)
{
        CME_LOG("INFO", name, " Started  ",  string (__FUNCTION__));
        return 0;
}

int mover_damo::move_hot(cme_context* ctx)
{
        CME_LOG("INFO", name, " Started  ",  string (__FUNCTION__));
        return start_damo_main(ctx, MOVE_HOT);
}

int mover_damo::move_cold(cme_context* ctx)
{
        CME_LOG("INFO", name, " Started  ",  string (__FUNCTION__));
        return start_damo_main(ctx, MOVE_COLD);
}

int mover_damo::move(cme_context* ctx)
{
        CME_LOG("INFO", name, " Started  ",  string (__FUNCTION__));
        return start_damo_main(ctx, MOVE);
}

int mover_damo::get_status()
{
        CME_LOG("INFO", name, " Started  ",  string (__FUNCTION__));
        return 0;
}

std::string mover_damo::get_stats(cme_context* ctx)
{
                CME_LOG("INFO", name, " Started  ",  string (__FUNCTION__));
		return stats_damo_main(ctx);
}

int mover_damo::stop(string app_name, long app_pid)
{
        CME_LOG("INFO", name, " Started  ",  string (__FUNCTION__));
        if (TEST_BUILD)
        {
                get_status();
        }
        return stop_damo_main(app_name, app_pid);
}

mover_damo::mover_damo (string _name)
{
  name = _name;
}

std::string mover_damo::get_name()
{
        return name;
}
