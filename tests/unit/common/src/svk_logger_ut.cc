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
  svk_logger_init("framework", LOG_FILE, TRACE, 1, 100, "rotating_file");
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(0, svk_logger("framework", DEBUG, input.c_str()));
  sleep(2);
  std::ifstream file(LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();

  EXPECT_EQ(true, data.find(input) != std::string::npos);
  EXPECT_EQ(true, data.find("debug") != std::string::npos);
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLogMessageWithRotatingFile) {
  std::string input = "Logging Test Message";
  svk_logger_init("framework", LOG_FILE, TRACE, 4, 10, "rotating_file");
  EXPECT_EQ(0, svk_logger("framework", CRITICAL, input.c_str()));
  svk_logger("framework", WARN, "Logging second message");
  // Read the file contents to check whether the message is logged
  // Since the second message is logged, the file should have gone through
  // rotation causing the first message in the rolled over file.
  std::ifstream file(LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true, data.find("Test Message") == std::string::npos);
  EXPECT_EQ(true, data.find("second message") != std::string::npos);
  system("rm -f testfw*.log");
}

TEST(SVKCommon, SVKLogMessageWithChangeLevel) {
  std::string input = "Logging Test Message";
  svk_logger_init("framework", LOG_FILE, TRACE, 1, 1024, "rotating_file");
  EXPECT_EQ(0, svk_logger("framework", WARN, input.c_str()));
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(0, svk_logger_change_log_level("framework", INFO));
  svk_logger("framework", DEBUG, "Logging second message");
  sleep(1);
  // Read the file contents to check whether the message is logged
  // Since the second message is logged after changing the level,
  // it shoud not be present
  std::ifstream file(LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();

  EXPECT_EQ(true, data.find("Test Message") != std::string::npos);
  EXPECT_EQ(true, data.find("second message") == std::string::npos);
  unlink(LOG_FILE);
}

TEST(SVKCommon, SVKLogMessageWithPeriodicFlush) {
  std::string data;
  svk_logger_init("framework", LOG_FILE, INFO, 10, 102400, "rotating_file");
  EXPECT_EQ(0, svk_logger_set_flush_interval(0));
  svk_logger("framework", INFO, "Logging message before flush");

  // Read the file contents to check whether the message is logged
  // Since the flush is not set, the messages should not be found
  std::ifstream file1(LOG_FILE);
  std::string data1((std::istreambuf_iterator<char>(file1)),
                    (std::istreambuf_iterator<char>()));
  file1.close();
  EXPECT_EQ(true,
            data1.find("Logging message before flush") == std::string::npos);

  // Now set the periodic flush with 2 seconds
  EXPECT_EQ(0, svk_logger_set_flush_interval(2));
  svk_logger("framework", INFO, "Logging message after periodic flush");
  sleep(3);
  // Read the file after 3 seconds to see whether the message is flushed
  std::ifstream file2(LOG_FILE);
  std::string data2((std::istreambuf_iterator<char>(file2)),
                    (std::istreambuf_iterator<char>()));
  file2.close();
  EXPECT_EQ(true, data2.find("Logging message after periodic flush") !=
                      std::string::npos);

  // Write the message with WARNING level to see if it is logged immediately
  svk_logger("framework", WARN,
             "Logging message after periodic flush with WARN");
  std::ifstream file3(LOG_FILE);
  std::string data3((std::istreambuf_iterator<char>(file3)),
                    (std::istreambuf_iterator<char>()));
  file3.close();
  EXPECT_EQ(true,
            data3.find("Logging message after periodic flush with WARN") !=
                std::string::npos);

  unlink(LOG_FILE);
}
