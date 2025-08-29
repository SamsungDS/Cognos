/**
 * @file mock_svk_publisher.h
 * @brief Mock implementation for SVK publisher.
 */

#ifndef _MOCK_SVK_PUBLISHER__H_
#define _MOCK_SVK_PUBLISHER__H_

#include "mock.h"

/**
 * @defgroup mock_svk_publisher Mock SVK Publisher
 * @{
 */

extern "C" {
/**
 * @brief Stub for publishing data.
 *
 * @param[in] topic         The topic to publish to.
 * @param[in] payload_data  The data to be published.
 * @param[in] data_len      The length of the data.
 * @return int              Always returns 0.
 */
DEFINE_STUB(publish_event_data_to_core, int,
            (char* topic, uint8_t* payload_data, uint64_t data_len), 0)
}

/** @} */  // end of mock_svk_publisher group

#endif  // _MOCK_SVK_PUBLISHER__H_