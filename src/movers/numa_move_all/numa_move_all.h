#ifndef __NUMA_MOVE_ALL_H__
#define __NUMA_MOVE_ALL_H__

#include "cme_mover.h"


class numa_move_all : public cme_mover
{
        public:
		numa_move_all(std::string);

                int move_all(long, unsigned int, unsigned int,  std::function<void(void*, int)>, void*, int) override;
                int move_hot() override;
                int move_cold() override;
                int move() override;
                int get_status() override;
                int stop() override;
                std::string get_name() override;
	private:
		std::string name;
};

#endif
