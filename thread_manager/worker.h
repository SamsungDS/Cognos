#ifndef __WORKER_H__
#define __WORKER_H__

#include <chrono>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

typedef std::vector<std::thread *> workerVectorGroup;
class WorkerSharedData;

typedef struct {
  std::string feature_name;
  std::string logic_module_name;
  std::string app_name;
  uint32_t numOps;
  uint32_t queueDepth;
  uint32_t numaNode;
  uint32_t ioType;            // r, w, rw
  uint32_t ioPattern;         // seq, rand, mixed
  uint64_t ioSize;            // bytes
  uint32_t statsRelayMethod;  // push - 0, pull - 1
  std::string device;
  std::string zmq_server;      // valid for push stats only
  std::string zmq_port;        // valid for push stats only
  std::string publish_prefix;  // valid for push stats only
} svk_slat_worker_logic_input;

typedef struct {
  uint64_t avgLatencyus;
  uint64_t iops;
  uint64_t bandwidthGBps;
  uint64_t avgReadLatency;
  uint64_t avgWriteLatency;
  uint64_t avgUpdateLatency;
  uint64_t avgReadIOPS;
  uint64_t avgWriteIOPS;
  uint64_t avgP99Latency;  // TBD
  uint64_t ioBytesRead;
  uint64_t ioBytesWritten;
  uint64_t ioBytesRewrite;
} svk_slat_logic_output;

using logic_fn = int (*)(WorkerSharedData *statStruct);

class WorkerSharedData {
 public:
  int workerCount;
  int workersInProgress;
  int workersFailed;
  int workersDone;
  bool threadNotifyFlag;  // notify all threads to stop/terminate during
                          // application close
  bool timeoutFlag;       // Timeout flag for the threads in case of time-bound
                          // activity
  int timeLimit;          // Time limit for the logic module to run
  std::mutex mutex;
  std::time_t startTime;
  svk_slat_worker_logic_input *slatInput;
  svk_slat_logic_output *slatOutput;
  logic_fn function_ptr;  // Function to run and return the the stats
};

class WorkerManager {
 public:
  WorkerManager(std::string svk_logic_logger_name, int threadCount,
                int timeLimit, svk_slat_worker_logic_input *slatInput,
                svk_slat_logic_output *slatOutput, logic_fn function_ptr);
  ~WorkerManager();
  int start();
  int stop();
  void notifyWorkers();
  void relayStats();
  int startWorker();
  int startWorkerAsync();
  int stopWorker();
  void incWorkerCount();
  void decWorkerCount();
  void setThreadTermFlag() { sharedData.threadNotifyFlag = true; };
  bool getThreadTermFlag() { return sharedData.threadNotifyFlag; };
  void setTimeoutFlag() { sharedData.timeoutFlag = true; };
  bool getTimeoutFlag() { return sharedData.timeoutFlag; };

 private:
  workerVectorGroup workerThreadGr;
  WorkerSharedData sharedData;
  std::string logic_logger_name;
};

#endif /* __WORKER_H__ */