#include <gtest/gtest.h>

#include "mock/mock_svk_publisher.h"
#include "ras_event_publisher.hpp"
#include "svk_logger.h"

TEST(EventPublisherUnitTest, TestCorretableErrorPublishSuccess) {
  int rc = 0;

  rc = cognos::ras::publisher::send_ras_threshold_warning_event("dummy_device",
                                                                "test message");
  EXPECT_EQ(rc, 0);
}

TEST(EventPublisherUnitTest, TestCorretableErrorPublishFailure) {
  int rc;
  MOCK_SET(publish_data, -1);
  rc = cognos::ras::publisher::send_ras_threshold_warning_event("dummy_device",
                                                                "test message");
  EXPECT_EQ(rc, -1);
  MOCK_CLEAR(publish_data);
}