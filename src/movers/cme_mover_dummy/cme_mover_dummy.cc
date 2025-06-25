#include "cme_mover_dummy.h"
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <thread>
#include <chrono>
#include <sstream>
#include <functional>

using namespace std;

extern "C" cme_mover* register_cme_fn() {

                cout << "Registering cme_mover_dummy " + string (__FUNCTION__) << endl;
                return new cme_mover_dummy("cme_mover_dummy");

}

extern "C" void unregister_cme_fn(cme_mover* mover_obj) {

        cout << "Unregistering cme mover_dummy " + string (__FUNCTION__) << endl;
        delete mover_obj;

}

int cme_mover_dummy::move_all(long target_pid, unsigned int node_src, unsigned int node_dest,  std::function<void(void*, int)> cbfn, void* cb_arg, int status)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        cout << "threadid=" << std::this_thread::get_id() << endl;
	std::this_thread::sleep_for(std::chrono::seconds(2));
	cbfn(cb_arg, status);
        return 0;
}

int cme_mover_dummy::move_hot(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}

int cme_mover_dummy::move_cold(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}
int cme_mover_dummy::move(string app_name, long app_pid, unsigned int slow_tier, unsigned int fast_tier, enum cme_mover_aggr aggresiveness_level)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}
int cme_mover_dummy::get_status()
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}
std::string cme_mover_dummy::get_stats(string app_name, long app_pid)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return "";
}
int cme_mover_dummy::stop(string app_name, long app_pid)
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}
cme_mover_dummy::cme_mover_dummy (string _name)
{
  name = _name;
}

std::string cme_mover_dummy::get_name()
{
        return name;
}
