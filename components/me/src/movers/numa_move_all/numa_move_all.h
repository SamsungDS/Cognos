#ifndef __NUMA_MOVE_ALL_H__
#define __NUMA_MOVE_ALL_H__

#include "cme_mover.h"

class numa_move_all : public cme_mover
{
        public:
		numa_move_all(std::string);

                int move_all(cme_context*) override;
                int move_hot(cme_context*) override;
                int move_cold(cme_context*) override;
                int move(cme_context*) override;
                int get_status() override;
                std::string get_stats(cme_context*) override;
                int stop(std::string, long) override;
                std::string get_name() override;
	private:
		std::string name;
};

#endif
