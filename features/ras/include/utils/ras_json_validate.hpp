#ifndef _RAS_JSON_VALIDATE_HPP_
#define _RAS_JSON_VALIDATE_HPP_

#include <nlohmann/json.hpp>
#include <string>

/**
 * @brief Validates a nested JSON object.
 *
 * @param obj The JSON object to be validated.
 * @param dot_seperated_key_hierarchy The dot-separated key hierarchy.
 * @return True if the JSON object is valid, false otherwise.
 */
bool validate_ras_nested_json(json& obj,
                              const std::string& dot_seperated_key_hierarchy);

/**
 * @brief Validates the incoming request.
 *
 * @param r The request to be validated.
 * @return True if the request is valid, false otherwise.
 */
bool validate_ras_json_request(
    json& r, const std::vector<std::string>& v_required_params);

#endif
