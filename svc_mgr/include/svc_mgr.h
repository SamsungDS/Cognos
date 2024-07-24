#ifndef __SVC_MGR_H__
#define __SVC_MGR_H__

#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <string>
#include <unordered_map>

#include "svc.h"
#include "svk_logger.h"

#define SVC_MGR_CONF_SECTION_TAG "svk_mgmt_fw_svc_mgr"
#define SVC_MGR_DEFAULT_FEATURE_SVC_DIR "feat_sm_svcs_dir"
#define SVC_MGR_NODE_DEFAULT_LOG_FILE "/var/log/svk/svk_mgmt_fw_svc_mgr.log"
#define SVC_MGR_LOGGER_MODULE_NAME "svc_mgr"
#define SVC_MGR_LOGGER_DEFAULT_FILE_COUNT 10
#define SVC_MGR_LOGGER_DEFAULT_FILE_SIZE 1048576ULL
#define SVC_MGR_LOGGER_DEFAULT_LEVEL "INFO"
#define SVC_MGR_LOGGER_DEFAULT_SINK_TYPE "rotating_file"

#define SM_STRINGIZE(s) std::string(s)

#define SVC_MGR_LOG0(lvl, p0) \
  svk_logger(SVC_MGR_LOGGER_MODULE_NAME, lvl, SM_STRINGIZE(p0).c_str())

#define SVC_MGR_LOG1(lvl, p0, p1)                \
  ({                                             \
    svk_logger(SVC_MGR_LOGGER_MODULE_NAME, lvl,  \
               (SM_STRINGIZE(p0) + p1).c_str()); \
  })

#define SVC_MGR_LOG2(lvl, p0, p1, p2)                 \
  ({                                                  \
    svk_logger(SVC_MGR_LOGGER_MODULE_NAME, lvl,       \
               (SM_STRINGIZE(p0) + p1 + p2).c_str()); \
  })

#define SVC_MGR_LOG3(lvl, p0, p1, p2, p3)                  \
  ({                                                       \
    svk_logger(SVC_MGR_LOGGER_MODULE_NAME, lvl,            \
               (SM_STRINGIZE(p0) + p1 + p2 + p3).c_str()); \
  })

#define SVC_MGR_LOG4(lvl, p0, p1, p2, p3, p4)                   \
  ({                                                            \
    svk_logger(SVC_MGR_LOGGER_MODULE_NAME, lvl,                 \
               (SM_STRINGIZE(p0) + p1 + p2 + p3 + p4).c_str()); \
  })

#define SVC_MGR_LOG5(lvl, p0, p1, p2, p3, p4, p5)                    \
  ({                                                                 \
    svk_logger(SVC_MGR_LOGGER_MODULE_NAME, lvl,                      \
               (SM_STRINGIZE(p0) + p1 + p2 + p3 + p4 + p5).c_str()); \
  })

#define SVC_MGR_LOG6(lvl, p0, p1, p2, p3, p4, p5, p6)                     \
  ({                                                                      \
    svk_logger(SVC_MGR_LOGGER_MODULE_NAME, lvl,                           \
               (SM_STRINGIZE(p0) + p1 + p2 + p3 + p4 + p5 + p6).c_str()); \
  })

#define SVC_MGR_LOG7(lvl, p0, p1, p2, p3, p4, p5, p6, p7)                      \
  ({                                                                           \
    svk_logger(SVC_MGR_LOGGER_MODULE_NAME, lvl,                                \
               (SM_STRINGIZE(p0) + p1 + p2 + p3 + p4 + p5 + p6 + p7).c_str()); \
  })

#define SVC_MGR_LOG8(lvl, p0, p1, p2, p3, p4, p5, p6, p7, p8)                \
  ({                                                                         \
    svk_logger(                                                              \
        SVC_MGR_LOGGER_MODULE_NAME, lvl,                                     \
        (SM_STRINGIZE(p0) + p1 + p2 + p3 + p4 + p5 + p6 + p7 + p8).c_str()); \
  })

#define SVC_MGR_LOG9(lvl, p0, p1, p2, p3, p4, p5, p6, p7, p8, p9)              \
  ({                                                                           \
    svk_logger(SVC_MGR_LOGGER_MODULE_NAME, lvl,                                \
               (SM_STRINGIZE(p0) + p1 + p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9) \
                   .c_str());                                                  \
  })

#define SVC_MGR_LOG_PARAMS_COUNT(...) \
  SVC_MGR_LOG_PARAMS_COUNT2(__VA_ARGS__, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0)
#define SVC_MGR_LOG_PARAMS_COUNT2(_0, _1, _2, _3, _4, _5, _6, _7, _8, _9, _, \
                                  ...)                                       \
  _

#define SM_CAT(A, B) SM_CAT2(A, B)
#define SM_CAT2(A, B) A##B

#define SVC_MGR_LOG(lvl, ...) \
  SM_CAT(SVC_MGR_LOG, SVC_MGR_LOG_PARAMS_COUNT(__VA_ARGS__))(lvl, __VA_ARGS__)

using svc_mgr_config = struct svc_mgr_config {
  std::string feat_sm_svcs_dir;
  std::string log_level;
  std::string log_filename;
  std::string log_sink_type;
  int log_file_count;
  uint64_t log_file_size;
};

const std::unordered_map<std::string, level_E> svc_mgr_log_level_map = {
    {"TRACE", level_E::TRACE},       {"DEBUG", level_E::DEBUG},
    {"INFO", level_E::INFO},         {"NOTICE", level_E::NOTICE},
    {"WARN", level_E::WARN},         {"ERROR", level_E::ERROR},
    {"CRITICAL", level_E::CRITICAL}, {"ALERT", level_E::ALERT},
    {"FATAL", level_E::FATAL},       {"OFF", level_E::OFF}};

/*
 * @brief Provides a framework to facilitate implementation of pluggable
 *        SVK services.
 * @details Dynamically loads a service by looking up and invoking
 *          register_svk_service() symbol from one or more SVK plugin
 *          libraries.
 */
class ServiceManager {
 public:
  ServiceManager(const std::string &svk_conf_file);
  ~ServiceManager();
  int ServicesRegister(void);
  int ServicesStart(void);
  void ServicesStop(void);
  int ServiceAdd(Service *svc);
  Service *ServiceFind(std::string svc_name);

 private:
  svc_mgr_config sm_config;
  std::unordered_map<std::string, Service *> sm_svcs;
};

int svc_mgr_server_start(std::string svk_conf_file, bool blocking);
void svc_mgr_signal_handler(int signal);

#endif
