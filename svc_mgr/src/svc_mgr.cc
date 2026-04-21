#include "svc_mgr.h"

#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <sys/inotify.h>
#include <sys/stat.h>

#include <atomic>
#include <cassert>
#include <csignal>
#include <iostream>
#include <set>

#include "absl/flags/flag.h"
#include "absl/flags/parse.h"
#include "absl/strings/str_format.h"
#include "svc.h"

#ifndef BUILD_TESTING
ABSL_FLAG(std::string, svk_conf_file, "", "svk configuration file to read");
#endif

int initialize_logger(const svc_mgr_config &config) {
  auto found = svc_mgr_log_level_map.find(config.log_level);
  if (found == svc_mgr_log_level_map.end()) {
    std::cout << "Matching log level for the [" << config.log_level
              << "] not found. Exiting" << std::endl;
    return -EINVAL;
  }

  if (svk_logger_init(SVC_MGR_LOGGER_MODULE_NAME, config.log_filename.c_str(),
                      found->second, config.log_file_count,
                      config.log_file_size,
                      config.log_sink_type.c_str()) == 0) {
    SVC_MGR_LOG(level_E::INFO, "Initialized Mgmt FW Service Manager logger");
    return 0;
  } else {
    std::cout << "Mgmt FW Service Manager logger initialization failed"
              << std::endl;
  }
  return -EINVAL;
}

int read_svk_conf_file(const std::string svk_conf_file,
                       svc_mgr_config *config) {
  namespace pt = boost::property_tree;

  try {
    pt::ptree root;
    pt::read_json(svk_conf_file, root);
    pt::ptree svc_mgr_config_pt = root.get_child(SVC_MGR_CONF_SECTION_TAG);

    try {
      pt::ptree svc_mgr_info_pt = svc_mgr_config_pt.get_child("svc_mgr");
      config->feat_sm_svcs_dir = svc_mgr_info_pt.get<std::string>(
          "feat_sm_svcs_dir", SVC_MGR_DEFAULT_FEATURE_SVC_DIR);
      pt::ptree logger_info_pt = svc_mgr_config_pt.get_child("logger");
      config->log_level = logger_info_pt.get<std::string>(
          "log_level", SVC_MGR_LOGGER_DEFAULT_LEVEL);
      config->log_filename = logger_info_pt.get<std::string>(
          "log_file_name", SVC_MGR_NODE_DEFAULT_LOG_FILE);
      config->log_file_count = logger_info_pt.get<uint64_t>(
          "log_file_count", SVC_MGR_LOGGER_DEFAULT_FILE_COUNT);
      config->log_file_size = logger_info_pt.get<uint64_t>(
          "log_file_size", SVC_MGR_LOGGER_DEFAULT_FILE_SIZE);
      config->log_sink_type = logger_info_pt.get<std::string>(
          "sink_type", SVC_MGR_LOGGER_DEFAULT_SINK_TYPE);
    } catch (std::exception &e) {
      std::cout
          << "Unable to read Logger section of Mgmt FW in SVK config. Error -> "
          << e.what() << std::endl;
      // Use defaults
      config->feat_sm_svcs_dir = SVC_MGR_DEFAULT_FEATURE_SVC_DIR;
      config->log_level = SVC_MGR_LOGGER_DEFAULT_LEVEL;
      config->log_filename = SVC_MGR_NODE_DEFAULT_LOG_FILE;
      config->log_file_count = SVC_MGR_LOGGER_DEFAULT_FILE_COUNT;
      config->log_file_size = SVC_MGR_LOGGER_DEFAULT_FILE_SIZE;
      config->log_sink_type = SVC_MGR_LOGGER_DEFAULT_SINK_TYPE;
    }
    return 0;
  } catch (std::exception &e) {
    std::cerr << "Unable to read SVK config. Error -> " << e.what()
              << std::endl;
  }

  return -EINVAL;
}

ServiceManager::ServiceManager(const std::string &svk_conf_file) {
  struct stat buf;
  int rc;

  if (stat(svk_conf_file.c_str(), &buf) != 0 ||
      (buf.st_mode & S_IFMT) != S_IFREG) {
    throw std::invalid_argument("Invalid path given for config file");
  }

  rc = read_svk_conf_file(svk_conf_file, &sm_config);
  if (rc < 0) {
    throw std::invalid_argument("Failed to read config file");
  }

  rc = initialize_logger(sm_config);
  if (rc != 0) {
    throw std::invalid_argument("Failed to create logger");
  }

  rc = ServicesRegister();
  if (rc != 0) throw std::invalid_argument("Service registration failed");
}

ServiceManager::~ServiceManager() {
  SVC_MGR_LOG(level_E::INFO, "Closing the logger instance as part of shutdown");
  svk_logger_close(SVC_MGR_LOGGER_MODULE_NAME);

  return;
}

bool isDirectory(std::string path) {
  struct stat entrystat;

  if (stat(path.c_str(), &entrystat)) return false;
  return S_ISDIR(entrystat.st_mode);
}

static int _load_services(std::string &feat_sm_svcs_dir,
                          ServiceManager *svc_mgr) {
  int rc;

  DIR *dirfp = opendir(feat_sm_svcs_dir.c_str());

  if (dirfp == nullptr) {
    SVC_MGR_LOG(level_E::ERROR, "Invalid feature service directory");
    return -EINVAL;
  }
  struct dirent *entry = readdir(dirfp);
  for (; entry != nullptr; entry = readdir(dirfp)) {
    std::string entry_name(entry->d_name);
    std::string feat_lib_suffix_so(".so");
    if (entry_name.compare(".") == 0 || entry_name.compare("..") == 0) continue;
    std::string dfpath = feat_sm_svcs_dir + std::string("/") + entry_name;
    if (isDirectory(dfpath)) _load_services(dfpath, svc_mgr);
    if (entry_name.size() < feat_lib_suffix_so.size() ||
        entry_name.compare(entry_name.size() - feat_lib_suffix_so.size(),
                           feat_lib_suffix_so.size(),
                           feat_lib_suffix_so) != 0) {
      continue;
    }

    std::string feature_lib_str = feat_sm_svcs_dir + "/" + entry_name;
    SVC_MGR_LOG(level_E::INFO,
                "Checking for register_svk_service in the library ",
                feature_lib_str);
    void *handle = dlopen(feature_lib_str.c_str(), RTLD_LAZY);
    if (!handle) {
      SVC_MGR_LOG(level_E::ERROR, "Failed to open ", feature_lib_str,
                  "Reason: ", dlerror());
      continue;
    }
    int (*register_svk_service)(ServiceManager *svc_mgr) =
        (int (*)(ServiceManager *svc_mgr))dlsym(handle, "register_svk_service");
    if (register_svk_service == nullptr) {
      SVC_MGR_LOG(level_E::ERROR, "cannot find any service in ", dlerror());
      continue;
    }
    rc = register_svk_service(svc_mgr);
    if (rc != 0)
      SVC_MGR_LOG(level_E::ERROR, "Service registration failed for ",
                  feature_lib_str);
  }
  return 0;
}

int ServiceManager::ServicesRegister(void) {
  int rc;

  rc = _load_services(sm_config.feat_sm_svcs_dir, this);
  return rc;
}

int ServiceManager::ServicesStart(void) {
  int rc;

  for (auto it : sm_svcs) {
    rc = it.second->ServiceStart();
    if (rc != 0) {
      SVC_MGR_LOG(level_E::ERROR, "Failed to start service ", it.first,
                  ", rc: ", std::to_string(rc));
    }
  }
  return 0;
}

void ServiceManager::ServicesStop(void) {
  SVC_MGR_LOG(level_E::INFO, "Stopping Services ");
  for (auto it : sm_svcs) it.second->ServiceStop();
}

int ServiceManager::ServiceAdd(Service *svc) {
  assert(svc != NULL && !svc->svc_name.empty());

  SVC_MGR_LOG(level_E::INFO, "Adding service ", svc->svc_name);
  sm_svcs[svc->svc_name] = svc;

  return 0;
}

Service *ServiceManager::ServiceFind(std::string svc_name) {
  assert(!svc_name.empty());

  auto it = sm_svcs.find(svc_name);
  if (it != sm_svcs.end()) return it->second;

  return NULL;
}

static std::atomic<int> gSVCMGRSignalStatus = -1;
void svc_mgr_signal_handler(int signal) {
  std::string logger_str;

  SVC_MGR_LOG(level_E::WARN, "Received signal ", std::to_string(signal));

  gSVCMGRSignalStatus.store(signal);
}

int svc_mgr_server_start(std::string svk_conf_file, bool blocking) {
  ServiceManager *svc_mgr;
  int rc;

  std::signal(SIGTERM, svc_mgr_signal_handler);
  std::signal(SIGINT, svc_mgr_signal_handler);
  std::signal(SIGABRT, svc_mgr_signal_handler);

  try {
    svc_mgr = new ServiceManager(svk_conf_file);
  } catch (std::exception &e) {
    std::cout << "Service Manager initialization failed, " << e.what()
              << std::endl;
    return -EINVAL;
  }
  rc = svc_mgr->ServicesStart();
  if (rc != 0) {
    SVC_MGR_LOG(level_E::INFO, "Failed to start services ");
    delete svc_mgr;
    return rc;
  }

  SVC_MGR_LOG(level_E::INFO, "Service Manager initialized, blocking now ");
  if (blocking == true) {
    while (gSVCMGRSignalStatus.load() == -1) sleep(5);
  }
  SVC_MGR_LOG(level_E::INFO, "Shutting down Service Manager");
  svc_mgr->ServicesStop();

  delete svc_mgr;

  return 0;
}

#ifndef BUILD_TESTING
int main(int argc, char **argv) {
  absl::ParseCommandLine(argc, argv);
  std::string svk_conf_file = absl::GetFlag(FLAGS_svk_conf_file);

  return svc_mgr_server_start(svk_conf_file, true);
}
#endif
