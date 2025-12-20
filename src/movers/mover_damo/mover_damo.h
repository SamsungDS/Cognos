#ifndef __MOVER_DAMO_H__
#define __MOVER_DAMO_H__

#include "cme_mover.h"
#include "cme_context.h"

class mover_damo : public cme_mover
{
        public:
		mover_damo(std::string);

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
                 const std::map<std::string, uint32_t> to_bytes = {
                                {"B", 1},
                                {"KB", 1000},
                                {"KiB", 1024},
                                {"MB", (1000 * 1000)},
                                {"MiB", (1024 * 1024)},
                                {"GB", (1000 * 1000 * 1000)},
                                {"GiB", (1024 * 1024 * 1024)}
                 };
};

#endif
