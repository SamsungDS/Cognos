#include "cme_profiler_dummy.h"
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include <thread>
#include <chrono>
#include <sstream>

using namespace std;

extern "C" cme_profiler* register_cme_fn() {

                cout << "Registering cme profiler_dummy " + string (__FUNCTION__) << endl;
                return new cme_profiler_dummy(std::string("cme_profiler_dummy"));

}

extern "C" void unregister_cme_profiler(cme_profiler* profiler_obj) {

        cout << "Unregistering cme profiler_dummy " + string (__FUNCTION__) << endl;
        delete profiler_obj;

}

int cme_profiler_dummy::profile_start()
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        cout << "threadid=" << std::this_thread::get_id() << endl;
        return 0;
}

int cme_profiler_dummy::profile_stop()
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}
 
int cme_profiler_dummy::get_status()
{
        cout << name << " Started  " <<  string (__FUNCTION__) << endl;
        return 0;
}

cme_profiler_dummy::cme_profiler_dummy (string _name)
{
  name = _name;
}

std::string cme_profiler_dummy::get_name()
{
        return name;
}

