#include "worker.h"

#include <cstring>
#include <ctime>
#include <future>

#include "svk_logger.h"

#define LOG_MSG_MAX 256

void WorkerManager::incWorkerCount() {
  std::lock_guard<std::mutex> lock(sharedData.mutex);
  (sharedData.workersInProgress)++;
  return;
}
void WorkerManager::decWorkerCount() {
  std::lock_guard<std::mutex> lock(sharedData.mutex);
  (sharedData.workersInProgress)--;
  return;
}

int WorkerManager::startWorker() {
  char log_msg[LOG_MSG_MAX];

  sprintf(log_msg, "startWorker fn called");
  svk_logger(logic_logger_name.c_str(), level_E::INFO, log_msg);
  incWorkerCount();
  sprintf(log_msg, "incWorkerCount fn called %d", sharedData.workersInProgress);
  svk_logger(logic_logger_name.c_str(), level_E::INFO, log_msg);
  this->sharedData.function_ptr(&(this->sharedData));
  decWorkerCount();
  sprintf(log_msg, "startWorker fn completed %d", sharedData.workersInProgress);
  svk_logger(logic_logger_name.c_str(), level_E::INFO, log_msg);
  return 0;
}

int WorkerManager::stopWorker() { return 0; }

/* WorkerManager related functions */
WorkerManager::WorkerManager(std::string svk_logic_logger_name, int threadCount,
                             int timeLimit,
                             svk_slat_worker_logic_input* slatInput,
                             svk_slat_logic_output* slatOutput,
                             logic_fn function_ptr) {
  workerThreadGr.reserve(threadCount);
  logic_logger_name = svk_logic_logger_name;
  sharedData.workerCount = threadCount;
  sharedData.workersInProgress = 0;
  sharedData.workersFailed = 0;
  sharedData.workersDone = 0;
  sharedData.timeLimit = timeLimit;
  sharedData.threadNotifyFlag = false;
  sharedData.timeoutFlag = false;
  sharedData.startTime = std::time(nullptr);
  sharedData.slatInput = slatInput;
  sharedData.slatOutput = slatOutput;
  sharedData.function_ptr = function_ptr;
}

WorkerManager::~WorkerManager() {
  // enable condition and the other flags
  setThreadTermFlag();
  setTimeoutFlag();

  // join all the threads
  stop();
}

int WorkerManager::start() {
  char log_msg[LOG_MSG_MAX];

  sharedData.startTime = std::time(nullptr);
  for (int i = 0; i < sharedData.workerCount; i++) {
    std::thread* thread = new std::thread(&WorkerManager::startWorker, this);
    workerThreadGr.push_back(thread);
  }
  std::time_t current_time = std::time(nullptr);

  std::this_thread::sleep_for(std::chrono::milliseconds(10));
  while (((current_time - sharedData.startTime) < sharedData.timeLimit) &&
         (getThreadTermFlag() == false)) {
    std::this_thread::sleep_for(std::chrono::seconds(1));
    current_time = std::time(nullptr);
  }
  sprintf(log_msg,
          "Either time-bound timeout or thread termination flag set to true");
  svk_logger(logic_logger_name.c_str(), level_E::INFO, log_msg);
  notifyWorkers();
  setTimeoutFlag();
  stop();
  return 0;
}

int WorkerManager::stop() {
  char log_msg[LOG_MSG_MAX];

  sprintf(log_msg, "Stopping all the threads");
  svk_logger(logic_logger_name.c_str(), level_E::INFO, log_msg);
  for (std::thread* thread : workerThreadGr) {
    if (thread->joinable()) {
      thread->join();
    }
  }
  sprintf(log_msg, "All the threads are stopped");
  svk_logger(logic_logger_name.c_str(), level_E::INFO, log_msg);
  return 0;
}

void WorkerManager::notifyWorkers() { setThreadTermFlag(); }
