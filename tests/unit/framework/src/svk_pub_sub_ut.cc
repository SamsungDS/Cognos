#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <gtest/internal/gtest-port.h>
#include <sys/stat.h>
#include <unistd.h>

#include <fstream>
#include <iostream>
#include <string>
#include <thread>

#include "svk_logger.h"
#include "svk_pub_sub_struct.h"
#include "svk_publisher.h"
#include "svk_zmq_api.h"

using ::testing::HasSubstr;

/**
 * Checks if a given string exists in the log file.
 *
 * @param search_str The string to search for in the log file.
 * @return True if the string is found in the log file, false otherwise.
 */
bool is_str_in_log(std::string file_name, std::string search_str) {
  // Check if the log file exists
  std::ifstream file(file_name);
  if (!file.good()) {
    std::string message = file_name + " doesn't exist";
    std::cout << message << std::endl;
    return false;
  }
  // Read the entire log file into a string
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));

  // Close the file
  file.close();

  // Check if the search string is found in the log file
  return data.find(search_str) != std::string::npos;
}

int create_config_file(const char *file_name, const char *transport_type,
                       const char *ip_address, const char *port) {
  char buffer[512];
  sprintf(buffer,
          "{\"pubsub\": {\"transport_type\": \"%s\",\"ip_address\": \"%s\", "
          "\"port\": %d, \"topics\": [\"metrics\", \"events\", \"alerts\"]}}",
          transport_type ? transport_type : "zmq",
          ip_address ? ip_address : "0",
          port ? atoi(port) : DEFAULT_PUB_SUB_PORT);
  FILE *fp = fopen(file_name, "w");
  EXPECT_NE(fp, nullptr);
  fwrite((void *)buffer, strlen(buffer), 1, fp);
  fclose(fp);
  return 0;
}

// This function creates subscriber socket with the IP and port tuple
// Also it creates multiple (2) topics if valid
int SpawnSubscriber(std::string &ip, std::string &port, std::string &topic1,
                    std::string &topic2, int &msg_count, int data_size,
                    std::string feature_name) {
  void *zmq_context;
  void *zmq_socket;
  svk_slat_logic_output data;
  int count = 0;

  int rc = zmq_init_subscriber(&zmq_context, &zmq_socket, ip.c_str(),
                               port.c_str(), topic1.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return -1;
  }
  if (topic2.length()) {
    rc = zmq_subscribe_topic(zmq_socket, topic2.c_str());
    EXPECT_EQ(rc, 0);
  }

  while (true) {
    rc = zmq_receive_data(zmq_socket, (uint8_t *)&data, data_size, true);
    if (rc == -1) {
      std::cout << "Failed to get data" << std::endl;
    } else {
      std::cout << "received data " << data.app_name << std::endl;
    }
    // Count the messages and then break depending on the input message count
    count++;
    if (count == msg_count) break;
  }

  zmq_cleanup_subscriber(zmq_context, zmq_socket);
  return 0;
}

TEST(SVKPubSubIntegrationTest, PubSubInitSuccess) {
  testing::internal::CaptureStdout();
  std::string sub_host = "localhost";
  std::string port = "5555";
  std::string topic1 = SVK_ZMQ_METRICS_FILTER_TOPIC;
  std::string topic2 = "";
  std::string feature = "core";
  std::string file = "/var/log/svk/svkpubsub.log";
  std::string config_file = "conf.json";
  int msg_count = 1;
  int rc;

  create_config_file(config_file.c_str(), nullptr, nullptr, nullptr);
  rc = svk_logger_init(feature.c_str(), file.c_str(), level_E::INFO, 1,
                       1024 * 1024, "rotating_file");
  EXPECT_EQ(rc, 0);

  std::thread *thread1 =
      new std::thread(&SpawnSubscriber, std::ref(sub_host), std::ref(port),
                      std::ref(topic1), std::ref(topic2), std::ref(msg_count),
                      sizeof(svk_slat_logic_output), std::ref(feature));

  svk_slat_logic_output data;
  payload_header topic_hdr;

  rc = initialize_publisher(config_file.c_str());
  EXPECT_EQ(rc, 0);

  strcpy(data.host_name, "localhost2");
  strcpy(data.device_name, "12");
  strcpy(data.app_name, "TESTAPP1");
  data.avgLatencyns = 1000;
  strcpy(topic_hdr.topic, topic1.c_str());
  topic_hdr.payload_len = sizeof(data);

  rc = publish_data((char *)topic1.c_str(), (uint8_t *)&data, sizeof(data));
  EXPECT_EQ(rc, 0);

  cleanup_publisher();

  thread1->join();
  svk_logger_close(feature.c_str());

  std::string output = testing::internal::GetCapturedStdout();
  std::cout << "STDOUT " << output << std::endl;

  EXPECT_THAT(output, HasSubstr("received data TESTAPP1"));
}

TEST(SVKPubSubUnitTest, PubSubInitSimpleCaseWithoutLoggerInit) {
  testing::internal::CaptureStdout();
  std::string config_file = "conf.json";

  int rc;

  rc = create_config_file(config_file.c_str(), "zmq", "127.0.0.1", "1111");
  EXPECT_EQ(rc, 0);

  // publisher struct null ptr
  rc = initialize_publisher(config_file.c_str());
  EXPECT_EQ(rc, 0);

  rc = cleanup_publisher();
  EXPECT_EQ(rc, 0);
  std::string output = testing::internal::GetCapturedStdout();
  std::cout << "STDOUT " << output << std::endl;

  EXPECT_THAT(
      output,
      HasSubstr("Created a publisher socket for the IP 127.0.0.1 port 1111"));
  EXPECT_THAT(output, HasSubstr("Successfully closed the publisher"));
}

TEST(SVKPubSubIntegrationTest, PubInitCalledTwice) {
  int rc;
  std::string feature = "core";
  std::string file = "/var/log/svk/svkpubsub.log";
  std::string config_file = "conf.json";

  unlink(file.c_str());
  rc = svk_logger_init(feature.c_str(), file.c_str(), level_E::INFO, 1,
                       1024 * 1024, "rotating_file");
  EXPECT_EQ(rc, 0);

  rc = create_config_file(config_file.c_str(), "zmq", nullptr, nullptr);
  EXPECT_EQ(rc, 0);

  rc = initialize_publisher(config_file.c_str());
  EXPECT_EQ(rc, 0);
  svk_logger_flush(feature.c_str());
  std::string log_msg = "Created a publisher socket for the IP 0 port 5555";
  EXPECT_EQ(true, is_str_in_log(file, log_msg));

  rc = initialize_publisher(config_file.c_str());
  EXPECT_EQ(rc, 0);
  svk_logger_flush(feature.c_str());
  log_msg = "Found the publisher socket already created for the IP 0 port 5555";
  EXPECT_EQ(true, is_str_in_log(file, log_msg));

  rc = cleanup_publisher();
  EXPECT_EQ(rc, 0);
  svk_logger_flush(feature.c_str());
  log_msg = "Successfully closed the publisher";
  EXPECT_EQ(true, is_str_in_log(file, log_msg));

  rc = cleanup_publisher();
  EXPECT_EQ(rc, 0);
  svk_logger_flush(feature.c_str());
  log_msg = "Publisher is already closed";
  EXPECT_EQ(true, is_str_in_log(file, log_msg));
}

TEST(SVKPubSubIntegrationTest, PubInitFailureCases) {
  int rc;
  std::string feature = "core";
  std::string file = "/var/log/svk/svkpubsub.log";
  std::string config_file = "conf.json";
  char buffer[256];

  unlink(file.c_str());
  rc = svk_logger_init(feature.c_str(), file.c_str(), level_E::INFO, 1,
                       1024 * 1024, "rotating_file");
  EXPECT_EQ(rc, 0);

  // Empty config_file passed
  rc = initialize_publisher("");
  EXPECT_EQ(rc, -1);

  // Config file as null pointer
  rc = initialize_publisher(nullptr);
  EXPECT_EQ(rc, -1);

  // Invalid config file
  rc = initialize_publisher("nullptr");
  EXPECT_EQ(rc, -1);

  // Invalid transport type
  rc = create_config_file(config_file.c_str(), "grpc", nullptr, nullptr);
  EXPECT_EQ(rc, 0);
  rc = initialize_publisher("nullptr");
  EXPECT_EQ(rc, -1);
  unlink(config_file.c_str());

  FILE *fp = fopen(config_file.c_str(), "w");
  EXPECT_NE(fp, nullptr);
  fclose(fp);

  rc = initialize_publisher(config_file.c_str());
  EXPECT_NE(rc, 0);

  rc = publish_data((char *)feature.c_str(), nullptr, 256);
  EXPECT_NE(rc, 0);

  rc = publish_data((char *)feature.c_str(), (uint8_t *)buffer, 0);
  EXPECT_NE(rc, 0);

  // Valid args, but the publisher functions are not initialized
  rc = publish_data((char *)feature.c_str(), (uint8_t *)buffer, 256);
  EXPECT_NE(rc, 0);

  // Check if the publisher functions are not initialized
  rc = cleanup_publisher();
  EXPECT_NE(rc, 0);

  // topic name is too big

  strcpy(buffer, "{}");

  fp = fopen(config_file.c_str(), "w");
  fwrite((void *)buffer, strlen(buffer), 1, fp);
  EXPECT_NE(fp, nullptr);
  fclose(fp);

  payload_header hdr;
  char invalid_topic_name[sizeof(hdr.topic) + 16];
  int i;
  for (i = 0; i < (int)sizeof(invalid_topic_name) - 1; i++) {
    invalid_topic_name[i] = 'D';
  }
  invalid_topic_name[i] = '\0';
  rc = initialize_publisher(config_file.c_str());
  EXPECT_EQ(rc, 0);
  rc = publish_data(invalid_topic_name, (uint8_t *)buffer, 256);
  EXPECT_NE(rc, 0);
  unlink(config_file.c_str());
}

TEST(SVKPubSubIntegrationTest, PubSubInitWithoutPubSubConfigSection) {
  testing::internal::CaptureStdout();
  std::string sub_host = DEFAULT_PUB_IP_ADDR;
  std::string port = std::to_string(DEFAULT_PUB_SUB_PORT);
  std::string topic1 = SVK_ZMQ_METRICS_FILTER_TOPIC;
  std::string topic2 = "";
  std::string feature = "core";
  std::string file = "/var/log/svk/svkpubsub.log";
  std::string config_file = "conf.json";
  int msg_count = 1;
  int rc;
  char buffer[] = "{}";

  FILE *fp = fopen(config_file.c_str(), "w");
  fwrite((void *)buffer, strlen(buffer), 1, fp);
  EXPECT_NE(fp, nullptr);
  fclose(fp);
  rc = svk_logger_init(feature.c_str(), file.c_str(), level_E::INFO, 1,
                       1024 * 1024, "rotating_file");
  EXPECT_EQ(rc, 0);
  svk_logger(feature.c_str(), level_E::INFO,
             "PubSubInitWithoutPubSubConfigSection");

  std::thread *thread1 =
      new std::thread(&SpawnSubscriber, std::ref(sub_host), std::ref(port),
                      std::ref(topic1), std::ref(topic2), std::ref(msg_count),
                      sizeof(svk_slat_logic_output), std::ref(feature));

  svk_slat_logic_output data;
  payload_header topic_hdr;

  rc = initialize_publisher(config_file.c_str());
  EXPECT_EQ(rc, 0);

  strcpy(data.host_name, "localhost3");
  strcpy(data.device_name, "13");
  strcpy(data.app_name, "TESTAPP3");
  data.avgLatencyns = 1000;
  strcpy(topic_hdr.topic, topic1.c_str());
  topic_hdr.payload_len = sizeof(data);

  rc = publish_data((char *)topic1.c_str(), (uint8_t *)&data, sizeof(data));
  EXPECT_EQ(rc, 0);

  cleanup_publisher();

  thread1->join();
  svk_logger_close(feature.c_str());

  std::string output = testing::internal::GetCapturedStdout();
  std::cout << "STDOUT " << output << std::endl;

  EXPECT_THAT(output, HasSubstr("received data TESTAPP3"));
}
