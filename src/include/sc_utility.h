#ifndef _UTILITY_H
#define _UTILITY_H

#include <string>

/**
 * @brief Generates a structured JSON error response based on a POSIX error
 * code.
 *
 * This function maps standard POSIX error codes (e.g., EINVAL, ENOENT) to
 * human-readable messages and formats them into a JSON response.
 *
 * @param[in] error_code The standard POSIX error code.
 * @param[in] custom_message An optional custom error message that overrides the
 * default.
 * @return A JSON string representing the error response.
 *
 * @example Example usage:
 * @code
 * std::string response = generate_error_response(EINVAL, "Invalid device_id
 * format");
 *  // Output: {"rc": "EINVAL", "message": "Invalid device_id format"}
 *  @endcode
 */
std::string posix_err_to_json(int error_code,
                              const std::string& custom_message = "");

/**
 * @brief Parses a ID string and converts it to a uint64_t.
 *
 * This function attempts to convert the given string representation of
 * a ID into a uint64_t value. It handles potential errors such as
 * invalid formats and out-of-range values by returning a structured error
 * response.
 *
 * @param[in] id_str The input device ID as a string.
 * @param[out] id The parsed device ID as a uint64_t.
 * @param[out] error_response JSON-formatted error response in case of failure.
 * @return true if parsing was successful, false if an error occurred.
 */
bool str_to_int(const std::string& id_str, uint64_t& id,
                std::string& error_response);

/**
 * @brief Flattens a JSON array into a comma-separated string.
 *
 * This function processes a JSON string, ensuring that if it is a valid array,
 * all its elements are extracted and concatenated into a single comma-separated
 * string without additional list nesting. If the input is a JSON object, it is
 * returned as is. If the input is not valid JSON, an error code is returned.
 *
 * @param[in] json_str The input JSON string (either an array or an object).
 * @param[out] A flattened JSON string
 * @return status success or error code.
 */
int json_arr_to_str(const std::string& json_str, std::string& flattened_result);

#endif
