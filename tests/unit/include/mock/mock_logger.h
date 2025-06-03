#ifndef _MOCK_LOGGER__H_
#define _MOCK_LOGGER__H_

#include <stdio.h>

#include "mock.h"
#include "svk_logger.h"
/**
 * @file mock_logger.h
 * @brief Mock logger header file for unit testing.
 */

/**
 * This macro is used to create a mock function for the svk_logger module.
 * It allows for the definition of a mock return value for testing purposes.
 *
 * @param function The function name (svk_logger).
 * @param return_type The return type of the mock function (int).
 */
DEFINE_RETURN_MOCK(svk_logger, int);
/**
 * @brief Mock implementation of the svk_logger function for unit testing.
 *
 * This function serves as a mock for the svk_logger module, allowing for
 * controlled testing of logging functionality. It takes in a feature name,
 * log level, and message, and returns an integer value based on the mock
 * implementation defined for testing purposes.
 *
 * @param feature The feature name for logging.
 * @param log_level The log level for the message.
 * @param message The log message.
 * @return An integer value representing the result of the mock logging
 * operation.
 */
int svk_logger(const char *feature, level_E log_level, const char *message) {
  printf("FEATURE[%s] : LOG LEVEL %d: %s\n", feature, log_level, message);
  return 0;
}
#endif  // _MOCK_LOGGER__H_