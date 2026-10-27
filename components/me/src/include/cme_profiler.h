#ifndef __CME_PROFILER_H__
#define __CME_PROFILER_H__

#include <map>
#include <mutex>
#include <unordered_map>
#include <string>

class cme_profiler
{
public:
        virtual ~cme_profiler() {}

        virtual std::string get_name() = 0;
        virtual int profile_start() = 0;
        virtual int profile_stop() = 0;
        virtual int get_status() = 0;
};

#endif
