#include <dirent.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <stdio.h>
#include <stdlib.h>

#include <csignal>
#include <thread>

#include "events_handler.h"

using ::testing::_;
using ::testing::AtLeast;
using ::testing::DoAll;
using ::testing::Return;
using ::testing::SetArgPointee;
using ::testing::StartsWith;
using ::testing::StrEq;

json create_json_event(std::string cluster_name, std::string node_name,
                       std::string data) {
  json event_data = {
      {"event_header",
       {{"cluster_name", cluster_name}, {"node_name", node_name}}},
      {"event_payload", {{"data", data}}}};

  return event_data;
}

TEST(EventHandler, InsertEventSuccess) {
  json event_data = create_json_event("c1", "n1", "c1_n1_d1");
  EXPECT_EQ(insert_event_to_controller_map(event_data), 0);
}

TEST(EventHandler, InsertEventFailure) {
  json event_data = create_json_event("c1", "", "c1_d1");
  EXPECT_NE(insert_event_to_controller_map(event_data), 0);
}

TEST(EventHandler, InsertEventWithoutClusterName) {
  json event_data = create_json_event("", "n1", "n1_d1");
  EXPECT_EQ(insert_event_to_controller_map(event_data), 0);
}

TEST(EventHandler, CircularQueueValidation) {
  json event_data = create_json_event("c1", "n1", "c1_n1_d1");
  EXPECT_EQ(insert_event_to_controller_map(event_data), 0);

  resize_event_queue(3);
  EXPECT_EQ(get_events_from_controller_map("", "", 0, -1, event_data), 0);
  EXPECT_EQ(event_data.size(), 1);

  event_data = create_json_event("c1", "n1", "c1_n1_d2");
  EXPECT_EQ(insert_event_to_controller_map(event_data), 0);
  event_data = create_json_event("c1", "n2", "c1_n2_d1");
  EXPECT_EQ(insert_event_to_controller_map(event_data), 0);
  event_data = create_json_event("c2", "n1", "c2_n1_d1");
  EXPECT_EQ(insert_event_to_controller_map(event_data), 0);

  EXPECT_EQ(get_events_from_controller_map("c1", "", 0, -1, event_data), 0);
  EXPECT_EQ(event_data.size(), 2);
  EXPECT_EQ(get_events_from_controller_map("c2", "", 0, -1, event_data), 0);
  EXPECT_EQ(event_data.size(), 1);
}

class EventHandlerSetup : public ::testing::Test {
 protected:
  EventHandlerSetup() { resize_event_queue(128); }

  void SetUp() override {
    json event_data = create_json_event("c1", "n1", "c1_n1_d1");
    EXPECT_EQ(insert_event_to_controller_map(event_data), 0);
    event_data = create_json_event("c1", "n1", "c1_n1_d2");
    EXPECT_EQ(insert_event_to_controller_map(event_data), 0);
    event_data = create_json_event("c1", "n2", "c1_n2_d1");
    EXPECT_EQ(insert_event_to_controller_map(event_data), 0);
    event_data = create_json_event("c2", "n1", "c2_n1_d1");
    EXPECT_EQ(insert_event_to_controller_map(event_data), 0);
  }

  void TearDown() override { clear_all_events_from_controller_map(); }
};

TEST_F(EventHandlerSetup, GetEvents) {
  json event_data;

  // Get all events
  EXPECT_EQ(get_events_from_controller_map("", "", 0, -1, event_data), 0);
  EXPECT_EQ(event_data.size(), 4);
}
