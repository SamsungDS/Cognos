#ifndef __cme_logger__
#define __cme_logger__

#include <iostream>
#include <cstdarg>
#include <string>
#include <sstream>
#include <utility>

// Helper function to concatenate strings to an ostringstream
template<typename T, typename... Args>
void concat_to_oss(std::ostringstream& oss, const T& first, const Args&... args);

// Base case for concat_to_oss
inline void concat_to_oss(std::ostringstream&, std::nullptr_t) {}

// Macro to log messages with a specified log level to std::cout
#define CME_LOG(level, ...) \
    do { \
        std::cout << "[" << level << "] "; \
        vlog_helper(__VA_ARGS__); \
        std::cout << std::endl; \
    } while (0)

// Macro to log error messages
#define CME_ERR(...) \
    do { \
        std::cerr << "[" << "ERROR" << "] "; \
        vlog_helper_err(__VA_ARGS__); \
        std::cerr << std::endl; \
    } while (0)

#define CME_ENTRY() CME_LOG("INFO", "Entering ", __FUNCTION__)
#define CME_EXIT() CME_LOG("INFO", "Exiting ", __FUNCTION__)

template<typename T, typename... Args>
void concat_to_oss(std::ostringstream& oss, const T& first, const Args&... args) {
    oss << first;
    concat_to_oss(oss, args...);
}

// Helper function to concatenate and print std::string arguments
template<typename... Args>
void vlog_helper(const Args&... args) {
    std::ostringstream oss;
    concat_to_oss(oss, args..., nullptr);
    std::cout << oss.str();
}

// Helper function to concatenate and print std::string arguments
template<typename... Args>
void vlog_helper_err(const Args&... args) {
    std::ostringstream oss;
    concat_to_oss(oss, args..., nullptr);
    std::cerr << oss.str();
}

#endif
