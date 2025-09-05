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

#include "mover_damo.h"
#include "damo_main.h"
#include "cme_utils.h"

using namespace std;

//int move(name, pid, slow_tier, fast_tier, aggresiveness_level) override;
int start_damo_main(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level, int move_select)
{
        int ret;
        try
        {
                ret = start(app_name, app_pid, slow_tier, fast_tier, aggresiveness_level, move_select);
        }
        catch (const std::exception& e)
        {
                cout << "Error in " + string(__FUNCTION__) + " : " + string(e.what()) << endl;
                ret = -EINVAL;
        }
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
                cout << "Error in " + string(__FUNCTION__) + " : " + string(e.what()) << endl;
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
                cout << "Error in " + string(__FUNCTION__) + " : " + string(e.what()) << endl;
                json_stats = to_string(-EINVAL);
        }
        return json_stats;
}

extern "C" cme_mover* register_cme_fn() {

                cout << "Registering cme_mover mover_damo " + string (__FUNCTION__) << endl;
                return new mover_damo(std::string("mover_damo"));

}

extern "C" void unregister_cme_fn(cme_mover* mover_obj) {

        cout << "Unregistering cme mover mover_damo " + string (__FUNCTION__) << endl;
        delete mover_obj;

}

int mover_damo::move_all(cme_context* ctx)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}

int mover_damo::move_hot(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return start_damo_main(app_name, app_pid, slow_tier, fast_tier, aggresiveness_level, MOVE_HOT);
}

int mover_damo::move_cold(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return start_damo_main(app_name, app_pid, slow_tier, fast_tier, aggresiveness_level, MOVE_COLD);
}

int mover_damo::move(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return start_damo_main(app_name, app_pid, slow_tier, fast_tier, aggresiveness_level, MOVE);
}

int mover_damo::get_status()
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}

std::string mover_damo::get_stats(cme_context* ctx)
{
                cout << name << " Started  " <<  string (__FUNCTION__) << endl;
		return stats_damo_main(ctx);
}

int mover_damo::stop(string app_name, long app_pid)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
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
