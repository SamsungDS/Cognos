#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <gtest/internal/gtest-port.h>
#include <sys/stat.h>
#include <unistd.h>

#include <fstream>
#include <iostream>
#include <string>
#include <thread>

#include "svk_zmq_api.h"

typedef struct {
  char host_name[64];
  char app_name[64];
  char device_name[64];   // This may contain just numa of device
  uint64_t avgLatencyns;  // Latency in nanoseconds
  uint64_t iops;
  uint64_t bandwidthGBps;
  uint64_t avgReadLatency;
  uint64_t avgWriteLatency;
  uint64_t avgUpdateLatency;
  uint64_t avgReadIOPS;
  uint64_t avgWriteIOPS;
  uint64_t avgP99Latency;
  uint64_t ioBytesRead;
  uint64_t ioBytesWritten;
  uint64_t ioBytesRewrite;
} svk_slat_logic_output;

using ::testing::HasSubstr;

// This function creates subscriber socket with the IP and port tuple
// Also it creates multiple (2) topics if valid
int SpawnSubscriber(std::string &ip, std::string &port, std::string &topic1,
                    std::string &topic2, int &msg_count, int data_size) {
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

TEST(SVKZMQIntegrationTest, InitSuccess) {
  testing::internal::CaptureStdout();
  std::string sub_host = "localhost";
  std::string port = "5555";
  std::string topic1 = "Topic1";
  std::string topic2 = "";
  int msg_count = 1;
  std::thread *thread1 = new std::thread(
      &SpawnSubscriber, std::ref(sub_host), std::ref(port), std::ref(topic1),
      std::ref(topic2), std::ref(msg_count), sizeof(svk_slat_logic_output));

  void *zmq_context;
  void *zmq_socket;
  svk_slat_logic_output data;
  payload_header topic_hdr;

  int rc = zmq_init_publisher(&zmq_context, &zmq_socket, "0", "5555");
  EXPECT_EQ(rc, 0);

  strcpy(data.host_name, "localhost2");
  strcpy(data.device_name, "12");
  strcpy(data.app_name, "TESTAPP2");
  data.avgLatencyns = 1000;
  strcpy(topic_hdr.topic, topic1.c_str());
  topic_hdr.payload_len = sizeof(data);

  rc = zmq_publish_data(zmq_socket, &topic_hdr, (uint8_t *)&data);
  EXPECT_EQ(rc, sizeof(data));

  zmq_cleanup_publisher(zmq_context, zmq_socket);

  thread1->join();

  std::string output = testing::internal::GetCapturedStdout();
  std::cout << "STDOUT " << output << std::endl;

  EXPECT_THAT(output, HasSubstr("received data TESTAPP2"));
}

TEST(SVKZMQIntegrationTest, InitSuccessWithDifferentFilters) {
  testing::internal::CaptureStdout();
  std::string sub_host = "localhost";
  std::string port = "5555";
  std::string topic1 = "Topic1";
  std::string topic2 = "Topic2";
  int msg_count = 2;
  std::thread *thread1 = new std::thread(
      &SpawnSubscriber, std::ref(sub_host), std::ref(port), std::ref(topic1),
      std::ref(topic2), std::ref(msg_count), sizeof(svk_slat_logic_output));

  void *zmq_context;
  void *zmq_socket;
  svk_slat_logic_output data;

  int rc = zmq_init_publisher(&zmq_context, &zmq_socket, "0", "5555");
  EXPECT_EQ(rc, 0);

  strcpy(data.host_name, "localhost1");
  strcpy(data.device_name, "1");
  strcpy(data.app_name, "TESTAPP1");
  data.avgLatencyns = 1000;
  // Set the first topic
  payload_header topic_hdr;
  strcpy(topic_hdr.topic, topic1.c_str());
  topic_hdr.payload_len = sizeof(data);

  rc = zmq_publish_data(zmq_socket, &topic_hdr, (uint8_t *)&data);
  EXPECT_EQ(rc, sizeof(data));

  strcpy(data.host_name, "localhost2");
  strcpy(data.device_name, "11");
  strcpy(data.app_name, "TESTAPP2");
  data.avgLatencyns = 1000;
  // Set the second topic
  strcpy(topic_hdr.topic, topic2.c_str());
  topic_hdr.payload_len = sizeof(data);

  rc = zmq_publish_data(zmq_socket, &topic_hdr, (uint8_t *)&data);
  EXPECT_EQ(rc, sizeof(data));

  zmq_cleanup_publisher(zmq_context, zmq_socket);

  thread1->join();

  std::string output = testing::internal::GetCapturedStdout();
  std::cout << "STDOUT " << output << std::endl;

  EXPECT_THAT(output, HasSubstr("received data TESTAPP1"));
  EXPECT_THAT(output, HasSubstr("received data TESTAPP2"));
}

int SocketCloseFn(void *zmq_context, void *zmq_subscriber) {
  std::cout << "Closing socket after 5 secs" << std::endl;
  sleep(5);
  int rc = zmq_cleanup_subscriber(zmq_context, zmq_subscriber);
  return rc;
}

TEST(SVKZMQIntegrationTest, SubscriberContextCleanup) {
  testing::internal::CaptureStdout();
  std::string sub_host = "localhost";
  std::string port = "5555";
  std::string topic1 = "Topic1";
  std::string topic2 = "Topic2";
  void *zmq_context;
  void *zmq_socket;
  svk_slat_logic_output data;
  bool flag = false;

  int rc = zmq_init_subscriber(&zmq_context, &zmq_socket, sub_host.c_str(),
                               port.c_str(), topic1.c_str());
  EXPECT_EQ(rc, 0);

  if (topic2.length()) {
    rc = zmq_subscribe_topic(zmq_socket, topic2.c_str());
    EXPECT_EQ(rc, 0);
  }

  std::thread *thread1 = new std::thread(&SocketCloseFn, std::ref(zmq_context),
                                         std::ref(zmq_socket));

  while (true) {
    rc = zmq_receive_data(zmq_socket, (uint8_t *)&data, sizeof(data), true);
    std::cout << "ERR - " << rc << std::endl;
    if (rc == -1) {
      std::cout << "Failed to get data" << std::endl;
      break;
    } else if (rc == -ETERM || rc == -EINTR || rc == -ENOTSOCK) {
      std::cout << "received TERM signal" << std::endl;
      flag = true;
      break;
    } else {
      std::cout << "received data " << data.app_name << std::endl;
    }
  }
  thread1->join();
  std::string output = testing::internal::GetCapturedStdout();
  std::cout << "STDOUT " << output << std::endl;
  EXPECT_EQ(flag, true);
  EXPECT_THAT(output, HasSubstr("received TERM signal"));
}

TEST(SVKZMQIntegrationTest, InitSubWithSmallSizeFail) {
  testing::internal::CaptureStdout();
  std::string sub_host = "localhost";
  std::string port = "5555";
  std::string topic1 = "Topic1";
  std::string topic2 = "";
  int msg_count = 1;
  std::thread *thread1 =
      new std::thread(&SpawnSubscriber, std::ref(sub_host), std::ref(port),
                      std::ref(topic1), std::ref(topic2), std::ref(msg_count),
                      sizeof(svk_slat_logic_output) - 10);

  void *zmq_context;
  void *zmq_socket;
  svk_slat_logic_output data;
  payload_header topic_hdr;

  int rc = zmq_init_publisher(&zmq_context, &zmq_socket, "0", "5555");
  EXPECT_EQ(rc, 0);

  strcpy(data.host_name, "localhost2");
  strcpy(data.device_name, "12");
  strcpy(data.app_name, "TESTAPP2");
  data.avgLatencyns = 1000;
  strcpy(topic_hdr.topic, topic1.c_str());
  topic_hdr.payload_len = sizeof(data);

  rc = zmq_publish_data(zmq_socket, &topic_hdr, (uint8_t *)&data);
  EXPECT_EQ(rc, sizeof(data));

  zmq_cleanup_publisher(zmq_context, zmq_socket);

  thread1->join();

  std::string output = testing::internal::GetCapturedStdout();
  std::cout << "STDOUT " << output << std::endl;

  EXPECT_THAT(output, HasSubstr("Failed to get data"));
}

TEST(SVKZMQIntegrationTest, InitSubWithSmallSizeFailMultipleMessages) {
  testing::internal::CaptureStdout();
  std::string sub_host = "localhost";
  std::string port = "5555";
  std::string topic1 = "Topic1";
  std::string topic2 = "";
  int msg_count = 2;
  std::thread *thread1 =
      new std::thread(&SpawnSubscriber, std::ref(sub_host), std::ref(port),
                      std::ref(topic1), std::ref(topic2), std::ref(msg_count),
                      sizeof(svk_slat_logic_output) - sizeof(payload_header));

  void *zmq_context;
  void *zmq_socket;
  svk_slat_logic_output data;
  payload_header topic_hdr;

  int rc = zmq_init_publisher(&zmq_context, &zmq_socket, "0", "5555");
  EXPECT_EQ(rc, 0);

  strcpy(data.host_name, "localhostFail1");
  strcpy(data.device_name, "12");
  strcpy(data.app_name, "TESTAPPFail1");
  data.avgLatencyns = 1000;
  strcpy(topic_hdr.topic, topic1.c_str());
  topic_hdr.payload_len = sizeof(data);

  rc = zmq_publish_data(zmq_socket, &topic_hdr, (uint8_t *)&data);
  EXPECT_EQ(rc, sizeof(data));

  strcpy(data.host_name, "localhostFail2");
  strcpy(data.device_name, "12");
  strcpy(data.app_name, "TESTAPPFail2");
  data.avgLatencyns = 1000;

  rc = zmq_publish_data(zmq_socket, &topic_hdr, (uint8_t *)&data);
  EXPECT_EQ(rc, sizeof(data));

  zmq_cleanup_publisher(zmq_context, zmq_socket);

  thread1->join();

  std::string output = testing::internal::GetCapturedStdout();
  std::cout << "STDOUT " << output << std::endl;

  EXPECT_THAT(output, HasSubstr("Failed to get data"));
}
