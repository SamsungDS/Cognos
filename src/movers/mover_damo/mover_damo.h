#ifndef __MOVER_DAMO_H__
#define __MOVER_DAMO_H__

#include "cme_mover.h"

class mover_damo : public cme_mover
{
        public:
		mover_damo(std::string);

                int move_all(long, unsigned int, unsigned int,  std::function<void(void*, int)>, void*, int) override;
                int move_hot(std::string,  long, unsigned int, unsigned int, enum cme_mover_aggr) override;
                int move_cold(std::string,  long, unsigned int, unsigned int, enum cme_mover_aggr) override;
                int move(std::string,  long, unsigned int, unsigned int, enum cme_mover_aggr) override;
                int get_status() override;
                int stop(std::string, long) override;
                std::string get_name() override;
	private:
		std::string name;
};

#endif
