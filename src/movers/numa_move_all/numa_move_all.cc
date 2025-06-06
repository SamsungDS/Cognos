#include "numa_move_all.h"
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

using namespace std;

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

                //cout << "src_nodes size " << src_nodes->size << endl;
                //cout << "dst_nodes size " << dst_nodes->size << endl;
                
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

int numa_move_all::move_all(long target_pid, unsigned int node_src, unsigned int node_dest, std::function<void(void*, int)> cbfn, void* cb_arg, int cmd_status)
{
        try
        {
                cout << name << " Started  " <<  string (__FUNCTION__) << endl;
                cout << "threadid=" << std::this_thread::get_id() << endl;
		int ret = _numa_move_all(target_pid, node_src, node_dest);
                cout << name << " Finished  " <<  string (__FUNCTION__) << "--"<< target_pid << "--" << node_src << "--" << node_dest << " ret = " << ret <<endl;
		cbfn(cb_arg, ret);
        }
        catch(const std::exception& e)
        {
                std::cerr << e.what() << '\n';
                return -1;
        }

        return 0;
}

int numa_move_all::move_hot(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, unsigned int aggresiveness_level)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}

int numa_move_all::move_cold(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, unsigned int aggresiveness_level)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}

int numa_move_all::move(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, unsigned int aggresiveness_level)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}

int numa_move_all::get_status()
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
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
