#include <gtest/gtest.h>
#include <sys/stat.h>
#include <unistd.h>

#include <fstream>
#include <iostream>
#include <string>

#include "svk_logger.h"

#define LOG_FILE "testfw.log"

int check_log_file() {
  struct stat fstat;
  int status = -1;
  if (stat(LOG_FILE, &fstat) == 0) {
    status = 0;
  }

  return status;
}

TEST(SVKCommon, SVKLoggerInit) {
  EXPECT_EQ(0, svk_logger_init("framework", LOG_FILE, TRACE, 2, 100,
                               "rotating_file"));
  EXPECT_EQ(0, check_log_file());
  unlink(LOG_FILE);
}
TEST(SVKCommon, SVKLoggerInitSyslog) {
  EXPECT_EQ(0, svk_logger_init("framework", LOG_FILE, OFF, 2, 100, "syslog"));
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLoggerInitInvalidLogSink) {
  EXPECT_EQ(-1,
            svk_logger_init("framework", LOG_FILE, TRACE, 2, 100, "syslogx"));
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLoggerInitNonexistDir) {
  EXPECT_EQ(0, svk_logger_init("framework", "varxyz/logx/testfw.log", ERROR, 2,
                               100, "rotating_file"));
  system("rm -rf varxyz");
}

TEST(SVKCommon, SVKLoggerInitNullFeaturePtr) {
  EXPECT_EQ(-1, svk_logger_init(nullptr, LOG_FILE, TRACE, 2, 100, "syslogx"));
}

TEST(SVKCommon, SVKLoggerInitNullFilenamePtr) {
  EXPECT_EQ(-1,
            svk_logger_init("framework", nullptr, TRACE, 2, 100, "syslogx"));
}

TEST(SVKCommon, SVKLoggerInitNullSinkTypePtr) {
  EXPECT_EQ(-1, svk_logger_init("framework", LOG_FILE, ERROR, 2, 100, nullptr));
}

TEST(SVKCommon, SVKLoggerReInit) {
  EXPECT_EQ(0, svk_logger_init("framework", LOG_FILE, TRACE, 2, 100,
                               "rotating_file"));
  EXPECT_EQ(0, svk_logger_init("framework", LOG_FILE, TRACE, 2, 100,
                               "rotating_file"));
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLoggerReInitSyslog) {
  EXPECT_EQ(0, svk_logger_init("framework", LOG_FILE, WARN, 2, 100, "syslog"));
  EXPECT_EQ(0, svk_logger_init("framework", LOG_FILE, WARN, 2, 100, "syslog"));
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLoggerChangeLevel) {
  EXPECT_EQ(0, svk_logger_init("framework", LOG_FILE, TRACE, 2, 100,
                               "rotating_file"));
  EXPECT_EQ(0, svk_logger_change_log_level("framework", CRITICAL));
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLoggerChangeLevelWithoutInit) {
  EXPECT_EQ(-1, svk_logger_change_log_level("framework", DEBUG));
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLoggerChangeLevelNullPtr) {
  EXPECT_EQ(-1, svk_logger_change_log_level(nullptr, DEBUG));
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLoggerWithoutInit) {
  EXPECT_EQ(-1, svk_logger("framework", DEBUG, "Dummy"));
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLoggerFeatureNullPtr) {
  EXPECT_EQ(-1, svk_logger(nullptr, DEBUG, "Dummy"));
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLoggerMessageNullPtr) {
  EXPECT_EQ(-1, svk_logger("framework", DEBUG, nullptr));
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLogDebugMessage) {
  std::string input = "Logging Test Message";
  std::string data;
  svk_logger_init("framework", LOG_FILE, TRACE, 1, 100, "rotating_file");
  EXPECT_EQ(0, svk_logger("framework", DEBUG, input.c_str()));
  std::ifstream file(LOG_FILE);
  data = file.get();
  file.close();
  EXPECT_EQ(0, data.find(input) != std::string::npos);
  EXPECT_EQ(0, data.find("DEBUG") != std::string::npos);
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLogMessageWithRotatingFile) {
  std::string input = "Logging Test Message";
  std::string data;
  svk_logger_init("framework", LOG_FILE, TRACE, 4, 10, "rotating_file");
  EXPECT_EQ(0, svk_logger("framework", CRITICAL, input.c_str()));
  svk_logger("framework", DEBUG, "Logging second message");
  // Read the file contents to check whether the message is logged
  // Since the second message is logged, the file should have gone through
  // rotation causing the first message in the rolled over file.
  std::ifstream file(LOG_FILE);
  data = file.get();
  file.close();
  EXPECT_EQ(false, data.find("Test Message") != std::string::npos);
  EXPECT_EQ(0, data.find("second message") != std::string::npos);
  system("rm -f testfw*.log");
}

TEST(SVKCommon, SVKLogMessageWithChangeLevel) {
  std::string input = "Logging Test Message";
  std::string data;
  svk_logger_init("framework", LOG_FILE, TRACE, 1, 1024, "rotating_file");
  EXPECT_EQ(0, svk_logger("framework", DEBUG, input.c_str()));
  EXPECT_EQ(0, svk_logger_change_log_level("framework", INFO));
  svk_logger("framework", DEBUG, "Logging second message");

  // Read the file contents to check whether the message is logged
  // Since the second message is logged after changing the level,
  // it shoud not be present
  std::ifstream file(LOG_FILE);
  data = file.get();
  file.close();
  EXPECT_EQ(0, data.find("Test Message") != std::string::npos);
  EXPECT_EQ(false, data.find("second message") != std::string::npos);
  unlink(LOG_FILE);
}
