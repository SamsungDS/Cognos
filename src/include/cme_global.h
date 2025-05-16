#ifndef __CME_GLOBAL_H__
#define __CME_GLOBAL_H__

#include "cme_context.h"
#include "cme_profiler.h"
#include "cme_mover.h"
#include "cme_utils.h"
#include <map>
#include <mutex>
#include <unordered_map>

const std::string CME_CONFIG_FILE = "/usr/local/svk/feature_modules/me/config/cme_config.json";

typedef enum
{
        CME_MOVER,
        CME_PROFILER,
        CME_INVALID_TYPE
} cme_type;

/**
 * @brief cme global class.
 * This is for the global cme object for the CME feature module.
 * THe lifetime of the cme global object is for the entire 
 * time cme plugin is  active.
 * It has the maps for list of profilers, list of movers
 * and list of cme contexts
 * Movers/profilers discovery, command handling is implemented
 * inside this class.
 *
 */
class cme_global
{
	typedef std::string (*CommandFunc) (cme_global*, unordered_map<string, string> &);
	public:
                cme_global ();
                unordered_map<std::string, cme_profiler*> profilers_list;
                unordered_map<std::string, cme_mover*> movers_list;
                std::string profilers_lib;
                std::string movers_lib;
                unordered_map<pair<std::string, unsigned long>, cme_context*, pair_hash> cme_contexts_list;
                mutex cme_contexts_mutex;
                int initialize();
                int cme_discovery();
                int read_cme_config_json(std::string);
                std::string cme_command_handler(std::string );
		void cme_contexts_lock ();
                void cme_contexts_unlock ();
        private:
                
                int _cme_discovery(std::string, int);
                void profiler_register(std::string, cme_profiler*);
		void mover_register(std::string, cme_mover*);
		std::map<std::string, CommandFunc> fw_hooks;
};

#endif
