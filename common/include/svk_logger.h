#ifndef __SVK_LOGGER_H__
#define __SVK_LOGGER_H__

#include <stdarg.h>
#include <stdint.h>

/**
 * Log Levels supported are in the following order
 * TRACE=0, DEBUG, INFO, NOTICE, WARN, ERROR, CRITICAL, ALERT, FATAL, OFF
 * Depending on the underlying logger module support, some of these levels can
 * be mapped to the similar level
 */
typedef enum {
  TRACE = 0,
  DEBUG,
  INFO,
  NOTICE,
  WARN,
  ERROR,
  CRITICAL,
  ALERT,
  FATAL,
  OFF
} level_E;

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief   This function creates a logger handle for the given parameters.
 * @param feature        Name of the feature registering the handle.
 * @param filename      Full path of the file. Make sure the directory
 * already exists.
 * @param base_log_level Base Log level. Messages logged with level equal or
 * above this will be logged. Refer to the supported log levels.
 * @param file_count    Total number of files in case of rotating file handle
 * @param file_size     Maximum size of each file in case of rotating file
 * @param sink_type     One of the following sink types - rotating_file,
 * syslog
 *
 * @return 0 on success, -1 on error
 */

int svk_logger_init(const char *feature, const char *filename,
                    level_E base_log_level, int file_count, uint64_t file_size,
                    const char *sink_type);

/**
 * @brief           Change the log level for the existing 'feature' to the
 * new base log level. Messages logged with level equal or above this will be
 * logged.
 * @param feature    feature name passed during initialization of logger
 * @param base_log_level New base Log level.
 *
 * @return 0 on success, -1 on error
 */
int svk_logger_change_log_level(const char *feature, level_E base_log_level);

/**
 * @brief           Logging function to log the message
 * @param feature    feature name passed during initialization of logger
 * @param log_level Log level between 0 and 8
 * @param message   message to be logged
 *
 * @return 0 on succes, -1 on error
 */
int svk_logger(const char *feature, level_E log_level, const char *message);

/**
 * @brief                 Enable periodic flush of the messages by the logger
 * @param flush_interval  Interval at which the messages will be flushed
 *
 * @return 0 on succes, -1 on error
 */
int svk_logger_set_flush_interval(int flush_interval);
#ifdef __cplusplus
}
#endif

#endif /*__SVK_LOGGER_H__*/