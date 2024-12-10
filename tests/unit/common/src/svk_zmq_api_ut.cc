#include <gtest/gtest.h>
#include <sys/stat.h>
#include <unistd.h>

#include <fstream>
#include <iostream>
#include <string>

#include "svk_zmq_api.h"

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

  if (len_ == sizeof(svk_slat_logic_output)) {
    memcpy(buffer, &data, sizeof(data));
    return len_;
  } else if (len_ == MAX_TOPIC_LEN - 1) {
    const char *topic = "test_topic";
    memcpy(buffer, topic, strlen(topic));
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
  int rc = initialize_pub(&ctx, &publisher, "*", "5555");
  EXPECT_EQ(0, rc);
  cleanup_zmq(&ctx, &publisher);
}

TEST(SVKZeroMQ, PublisherInitFail) {
  void *ctx;
  void *publisher;
  int rc = initialize_pub(&ctx, &publisher, "fail", "");
  EXPECT_EQ(-1, rc);
}

TEST(SVKZeroMQ, PublisherSend) {
  void *ctx;
  void *publisher;
  int rc = initialize_pub(&ctx, &publisher, "*", "5555");
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
  rc = publish(&publisher, "test_topic", &data);
  EXPECT_NE(-1, rc);
  cleanup_zmq(&ctx, &publisher);
}

TEST(SVKZeroMQ, PublisherSendInvalidSocket) {
  void *publisher = nullptr;
  svk_slat_logic_output data;

  int rc = publish(&publisher, "topic", &data);
  EXPECT_EQ(-1, rc);
}

TEST(SVKZeroMQ, PublisherSendInvalidData) {
  void *ctx;
  void *publisher;
  int rc = initialize_pub(&ctx, &publisher, "*", "5555");
  EXPECT_EQ(0, rc);

  svk_slat_logic_output data;
  svk_slat_logic_output *inv_data = nullptr;
  rc = publish(&publisher, "", &data);
  EXPECT_EQ(-1, rc);

  rc = publish(&publisher, "topic", inv_data);
  EXPECT_EQ(-1, rc);
}

/** Subscriber tests */
TEST(SVKZeroMQ, SubscriberInit) {
  void *ctx;
  void *subscriber;
  int rc = initialize_sub(&ctx, &subscriber, "localhost", "5555", "test_topic");

  EXPECT_EQ(0, rc);

  rc = set_socket_filters(&subscriber, "new_topic");
  EXPECT_EQ(0, rc);
  cleanup_zmq(&ctx, &subscriber);
}

TEST(SVKZeroMQ, SubscriberInitFail) {
  void *ctx;
  void *subscriber;
  int rc = initialize_sub(&ctx, &subscriber, "", "", "");
  EXPECT_EQ(-1, rc);
}

TEST(SVKZeroMQ, SubscriberGetData) {
  void *c;
  void *subscriber;
  int rc = initialize_sub(&c, &subscriber, "localhost", "5555", "test_topic");
  EXPECT_EQ(0, rc);

  svk_slat_logic_output recv_data;
  rc = get_data(&subscriber, &recv_data);
  EXPECT_EQ(sizeof(svk_slat_logic_output) + MAX_TOPIC_LEN - 1, rc);

  cleanup_zmq(&c, &subscriber);
}

TEST(SVKZeroMQ, SubscriberGetDataFail) {
  void *s = nullptr;

  svk_slat_logic_output data;

  int rc = get_data(&s, &data);
  EXPECT_EQ(-1, rc);
}

TEST(SVKZeroMQ, CleanupZMQ) {
  void *ctx;
  void *publisher;
  int rc = initialize_pub(&ctx, &publisher, "*", "5555");
  EXPECT_EQ(0, rc);

  rc = cleanup_zmq(&ctx, &publisher);
  EXPECT_EQ(0, rc);
}
