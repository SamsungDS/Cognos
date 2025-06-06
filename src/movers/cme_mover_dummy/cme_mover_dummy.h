#ifndef __CME_MOVER_DUMMY_H__
#define __CME_MOVER_DUMMY_H_

#include "cme_mover.h"

class cme_mover_dummy : public cme_mover
{
        public:
                cme_mover_dummy (std::string);
                std::string name;
                
                int move_all(long, unsigned int, unsigned int,  std::function<void(void*, int)>, void*, int) override;
                int move_hot(std::string,  long, unsigned int, unsigned int, unsigned int) override;
                int move_cold(std::string,  long, unsigned int, unsigned int, unsigned int) override;
                int move(std::string,  long, unsigned int, unsigned int, unsigned int) override;
                int get_status() override;
                int stop(std::string, long) override;
                std::string get_name() override;

};

#endif
