#include <gtest/gtest.h>
#include <sys/stat.h>
#include <unistd.h>

#include <fstream>
#include <iostream>
#include <string>

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

#define MOCK_STRUCT_INIT(...) \
  { __VA_ARGS__ }

#define DEFINE_RETURN_MOCK(fn, ret) \
  bool ut_##fn##_mocked = false;    \
  ret ut_##fn

DEFINE_RETURN_MOCK(zmq_send, int);
int zmq_send(void *s_, const void *buf_, size_t len_, int flags_) {
  if (len_ == 0) {
    return -1;
  }
  return 0;
}

DEFINE_RETURN_MOCK(zmq_recv, int);
int zmq_recv(void *s_, void *buf_, size_t len_, int flags_) {
  if (len_ == 1 || s_ == nullptr) {
    return -1;
  }
  svk_slat_logic_output data = {.host_name = "test_host",
                                .app_name = "test_app",
                                .device_name = "test_dev",
                                .avgLatencyns = 1,
                                .iops = 1,
                                .avgReadLatency = 1,
                                .avgWriteLatency = 1,
                                .avgUpdateLatency = 1,
                                .avgReadIOPS = 1,
                                .avgWriteIOPS = 1,
                                .avgP99Latency = 1,
                                .ioBytesRead = 1,
                                .ioBytesWritten = 1,
                                .ioBytesRewrite = 1};
  char *buffer = (char *)buf_;
  payload_header topic_hdr;
  if (len_ == sizeof(svk_slat_logic_output)) {
    memcpy(buffer, &data, sizeof(data));
    return len_;
  } else if (len_ == sizeof(payload_header)) {
    strcpy(topic_hdr.topic, "test_topic");
    topic_hdr.payload_len = sizeof(data);
    memcpy(buffer, &topic_hdr, sizeof(topic_hdr));
    return len_;
  }

  return -1;
}

DEFINE_RETURN_MOCK(zmq_getsockopt, int);
int zmq_getsockopt(void *s_, int option_, void *optval_, size_t *optvallen_) {
  if (s_) {
    int *rcv_more = (int *)optval_;
    *rcv_more = 1;
    return 0;
  }
  return -1;
}

/** Publisher tests */
TEST(SVKZeroMQ, PublisherInit) {
  void *ctx;
  void *publisher;
  int rc = zmq_init_publisher(&ctx, &publisher, "*", "5555");
  EXPECT_EQ(0, rc);
  zmq_cleanup_publisher(ctx, publisher);
}

TEST(SVKZeroMQ, PublisherInitFail) {
  void *ctx;
  void *publisher;
  int rc = zmq_init_publisher(&ctx, &publisher, "fail", "");
  EXPECT_EQ(-1, rc);

  rc = zmq_init_publisher(&ctx, &publisher, "127.0.0.1", "");
  EXPECT_EQ(-1, rc);
}

TEST(SVKZeroMQ, PublisherSend) {
  void *ctx;
  void *publisher;
  payload_header topic_hdr;
  int rc = zmq_init_publisher(&ctx, &publisher, "*", "5555");
  EXPECT_EQ(0, rc);

  svk_slat_logic_output data = {.host_name = "test_host",
                                .app_name = "test_app",
                                .device_name = "test_dev",
                                .avgLatencyns = 1,
                                .iops = 1,
                                .avgReadLatency = 1,
                                .avgWriteLatency = 1,
                                .avgUpdateLatency = 1,
                                .avgReadIOPS = 1,
                                .avgWriteIOPS = 1,
                                .avgP99Latency = 1,
                                .ioBytesRead = 1,
                                .ioBytesWritten = 1,
                                .ioBytesRewrite = 1};
  strcpy(topic_hdr.topic, "test_topic");
  topic_hdr.payload_len = sizeof(data);
  rc = zmq_publish_data(publisher, &topic_hdr, (uint8_t *)&data);
  EXPECT_NE(-1, rc);
  zmq_cleanup_publisher(ctx, publisher);
}

TEST(SVKZeroMQ, PublisherSendInvalidSocket) {
  void *publisher = nullptr;
  svk_slat_logic_output data;
  payload_header topic_hdr;
  strcpy(topic_hdr.topic, "test_topic");
  topic_hdr.payload_len = sizeof(data);

  int rc = zmq_publish_data(publisher, &topic_hdr, (uint8_t *)&data);
  EXPECT_EQ(-1, rc);
}

TEST(SVKZeroMQ, PublisherSendInvalidData) {
  void *ctx;
  void *publisher;
  int rc = zmq_init_publisher(&ctx, &publisher, "*", "5555");
  EXPECT_EQ(0, rc);
  payload_header topic_hdr;

  svk_slat_logic_output data;
  svk_slat_logic_output *inv_data = nullptr;
  // Empty topic in the header
  strcpy(topic_hdr.topic, "");
  topic_hdr.payload_len = sizeof(data);
  rc = zmq_publish_data(publisher, &topic_hdr, (uint8_t *)&data);
  EXPECT_EQ(0, rc);
  // null data
  strcpy(topic_hdr.topic, "Topic");
  rc = zmq_publish_data(publisher, &topic_hdr, (uint8_t *)inv_data);
  EXPECT_EQ(-1, rc);

  // payload len is zero
  strcpy(topic_hdr.topic, "Topic");
  topic_hdr.payload_len = 0;
  rc = zmq_publish_data(publisher, &topic_hdr, (uint8_t *)&data);
  EXPECT_EQ(-1, rc);
}

/** Subscriber tests */
TEST(SVKZeroMQ, SubscriberInit) {
  void *ctx;
  void *subscriber;
  int rc =
      zmq_init_subscriber(&ctx, &subscriber, "127.0.0.1", "5555", "test_topic");
  EXPECT_EQ(0, rc);

  rc = zmq_subscribe_topic(subscriber, "new_topic");
  EXPECT_EQ(0, rc);
  zmq_cleanup_publisher(ctx, subscriber);
}

TEST(SVKZeroMQ, SubscriberInitFail) {
  void *ctx;
  void *subscriber;
  int rc = zmq_init_subscriber(&ctx, &subscriber, "", "", "");
  EXPECT_EQ(-1, rc);
  rc = zmq_init_subscriber(&ctx, &subscriber, "127.0.0.1", "", "test_topic");
  EXPECT_EQ(-1, rc);
  rc = zmq_init_subscriber(nullptr, &subscriber, "127.0.0.1", "", "test_topic");
  EXPECT_EQ(-1, rc);
  rc = zmq_init_subscriber(&ctx, nullptr, "127.0.0.1", "", "test_topic");
  EXPECT_EQ(-1, rc);
}

TEST(SVKZeroMQ, SubscriberInitWithoutTopic) {
  void *ctx;
  void *subscriber;
  int rc = zmq_init_subscriber(&ctx, &subscriber, "127.0.0.1", "5555", "");
  EXPECT_EQ(0, rc);
  zmq_cleanup_publisher(ctx, subscriber);
  rc = zmq_init_subscriber(&ctx, &subscriber, "127.0.0.1", "5555", nullptr);
  EXPECT_EQ(0, rc);
  zmq_cleanup_publisher(ctx, subscriber);
}

TEST(SVKZeroMQ, SubscriberGetDataNonBlocking) {
  void *c;
  void *subscriber;
  int rc =
      zmq_init_subscriber(&c, &subscriber, "localhost", "5555", "test_topic");
  EXPECT_EQ(0, rc);

  svk_slat_logic_output recv_data;
  rc = zmq_receive_data(subscriber, (uint8_t *)&recv_data, sizeof(recv_data),
                        false);
  EXPECT_EQ(sizeof(svk_slat_logic_output), rc);

  zmq_cleanup_publisher(c, subscriber);
}

// Since this function is modified to zmq::poll, it will get stuck.
// Validating this in integration mode
// TEST(SVKZeroMQ, SubscriberGetData) {
//   void *c;
//   void *subscriber;
//   int rc = zmq_init_subscriber(&c, &subscriber, "localhost", "5555",
//   "test_topic"); EXPECT_EQ(0, rc);

//   svk_slat_logic_output recv_data;
//   rc = zmq_receive_data(subscriber, (uint8_t *)&recv_data,
//   sizeof(recv_data), true); EXPECT_EQ(sizeof(svk_slat_logic_output), rc);

//   zmq_cleanup_publisher(c, subscriber);
// }

TEST(SVKZeroMQ, SubscriberGetDataFail) {
  void *s = nullptr;
  svk_slat_logic_output data;

  int rc = zmq_receive_data(s, (uint8_t *)&data, sizeof(data), true);
  EXPECT_EQ(-1, rc);

  void *c;
  rc = zmq_init_subscriber(&c, &s, "localhost", "5555", "test_topic");
  EXPECT_EQ(0, rc);

  rc = zmq_receive_data(s, nullptr, sizeof(data), true);
  EXPECT_EQ(-1, rc);

  rc = zmq_receive_data(s, (uint8_t *)&data, 0, true);
  EXPECT_EQ(-1, rc);
  zmq_cleanup_subscriber(c, s);
}

TEST(SVKZeroMQ, CleanupPub) {
  void *ctx;
  void *publisher;
  int rc = zmq_init_publisher(&ctx, &publisher, "*", "5555");
  EXPECT_EQ(0, rc);

  rc = zmq_cleanup_publisher(ctx, publisher);
  EXPECT_EQ(0, rc);
}

TEST(SVKZeroMQ, CleanupSub) {
  void *ctx;
  void *subscriber;
  int rc =
      zmq_init_subscriber(&ctx, &subscriber, "127.0.0.1", "5555", "test_topic");
  EXPECT_EQ(0, rc);

  rc = zmq_cleanup_subscriber(ctx, subscriber);
  EXPECT_EQ(0, rc);
}
