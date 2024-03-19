#include "svk_logger.h"

#include <spdlog/spdlog.h>
#include <spdlog/sinks/basic_file_sink.h>
#include <spdlog/sinks/rotating_file_sink.h>
#include <spdlog/sinks/syslog_sink.h>
#include <stdarg.h>

#include <iostream>
#include <map>

typedef spdlog::level::level_enum spd_level_E;

spd_level_E
map_user_log_level_to_libray_log_level (level_E level)
{
  spd_level_E val;
  switch (level)
    {
    case TRACE:
      val = spdlog::level::trace;
      break;
    case DEBUG:
      val = spdlog::level::debug;
      break;
    case INFO:
    case NOTICE:
      val = spdlog::level::info;
      break;
    case WARN:
      val = spdlog::level::warn;
      break;
    case ERROR:
      val = spdlog::level::err;
      break;
    case CRITICAL:
    case ALERT:
    case FATAL:
      val = spdlog::level::critical;
      break;
    case OFF:
      val = spdlog::level::off;
      break;
    }
  return val;
}

int
svk_logger_init (const char *feature, const char *filename,
                 level_E base_log_level, int file_count, uint64_t file_size,
                 const char *sink_type)
{
  if (feature == nullptr || filename == nullptr || sink_type == nullptr
      || file_size == 0 || file_count == 0)
    {
      std::cout << "Invalid arguments given for one of these feature <"
                << feature << "> filename <" << filename << "> sink_type <"
                << sink_type << ">" << std::endl;
      return -1;
    }

  try
    {
      auto svk_logger = spdlog::get (feature);
      if (svk_logger)
        {
          svk_logger->log (spdlog::level::info, "Logger {} already created",
                           feature);
          return 0;
        }
      if (strcmp (sink_type, "rotating_file") == 0)
        {
          svk_logger = spdlog::rotating_logger_mt (feature, filename,
                                                   file_size, file_count);
        }
      else if (strcmp (sink_type, "syslog") == 0)
        {
          std::string ident = feature;
          pid_t log_pid = getpid ();
          svk_logger = spdlog::syslog_logger_mt (feature, ident, log_pid);
        }
      else
        {
          std::cout
              << "Log initialization failed - Invalid log sink type given "
              << sink_type << std::endl;
        }

      if (svk_logger == nullptr)
        {
          std::cout << "Log initialization failed" << sink_type << std::endl;
          throw std::invalid_argument (
              "svk_log_init failed - Logger creation failed");
        }

      spd_level_E level
          = map_user_log_level_to_libray_log_level (base_log_level);

      svk_logger->set_level (level);
    }
  catch (std::exception &ex)
    {
      std::cout << "Log initialization (spdlog) failed: " << ex.what ()
                << std::endl;
      return -1;
    }

  return 0;
}

int
svk_logger_change_log_level (const char *feature, level_E base_log_level)
{
  if (feature == nullptr)
    {
      spdlog::log (spdlog::level::err, "Feature argument is null");
      return -1;
    }

  try
    {
      auto svk_logger = spdlog::get (feature);
      if (svk_logger == nullptr)
        {
          spdlog::log (spdlog::level::err, "Logger for feature {} not found",
                       feature);
          throw std::invalid_argument ("Logger for the feature not found");
        }

      spd_level_E curr_level = svk_logger->level ();
      spd_level_E new_level
          = map_user_log_level_to_libray_log_level (base_log_level);
      svk_logger->set_level (new_level);
      svk_logger->log (spdlog::level::info,
                       "Log level for feature {} is changed from {} to {}",
                       feature, curr_level, new_level);
    }
  catch (std::exception &ex)
    {
      std::cout << "Exception in changing log_level from spdlog for feature "
                << feature << ": " << ex.what () << std::endl;
      return -1;
    }

  return 0;
}

int
svk_logger (const char *feature, level_E log_level, const char *message)
{
  if (feature == nullptr || message == nullptr)
    {
      spdlog::log (spdlog::level::err, "Feature or message argument is null");
      return -1;
    }

  try
    {
      auto svk_logger = spdlog::get (feature);
      if (svk_logger == nullptr)
        {
          spdlog::log (spdlog::level::err, "Logger for feature {} not found",
                       feature);
          throw std::invalid_argument ("Logger for the feature not found");
        }
      spd_level_E level = map_user_log_level_to_libray_log_level (log_level);
      svk_logger->log (level, message);
    }
  catch (std::exception &ex)
    {
      std::cout << "Exception in logging (spdlog) the message " << message
                << "for feature " << feature << ": " << ex.what ()
                << std::endl;
      return -1;
    }

  return 0;
}
