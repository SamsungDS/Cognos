#ifndef __CME_PROFILER_DUMMY_H__
#define __CME_PROFILER_DUMMY_H__

#include "cme_profiler.h"


class cme_profiler_dummy : public cme_profiler
{
        public:
                cme_profiler_dummy (std::string);
                std::string name;

                int profile_start() override;
                int profile_stop() override;
                int get_status() override;       
                std::string get_name() override;
};

#endif

