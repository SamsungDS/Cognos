#include "logicmock.h"

#include <boost/property_tree/json_parser.hpp>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>

#include "ras.hpp"

#define MOCK_MODULE_NAME "mock"

svk_status execute_mock_logic_sync(svk_logic_cmd *cmd, svk_logic_input *input,
                                   svk_logic_output *output) {
  svk_status ret = SVK_STATUS_SUCCESS;
  std::string slog;
  std::stringstream ss;
  slog.assign("mock logic sync");
  svk_logger(RAS_LOGGER, level_E::INFO, slog.c_str());

  if (cmd == nullptr || input == nullptr || output == nullptr) {
    ss << "cmd:" << cmd << " input:" << input << " output:" << output;
    slog.assign("Invalid input for mock logic sync params. " + ss.str());
    svk_logger(RAS_LOGGER, level_E::INFO, slog.c_str());
    return SVK_STATUS_FAIL;
  }

  if (input->input_buffer == nullptr) {
    slog.assign("NULL input buffer for mock logic sync params");
    svk_logger(RAS_LOGGER, level_E::INFO, slog.c_str());
    return SVK_STATUS_FAIL;
  }

  boost::property_tree::ptree pt;
  std::string in, out, sts;
  output->status = SVK_STATUS_FAIL;
  ret = SVK_STATUS_FAIL;

  in.assign((const char *)input->input_buffer);
  out = processRequest(in);

  try {
    ss.str(std::string());
    ss << out;
    boost::property_tree::read_json(ss, pt);
    snprintf((char *)output->output_buffer, output->output_len, "%s",
             out.c_str());
    if (pt.get<std::string>("result.commandSuccessful") == "true") {
      output->status = SVK_STATUS_SUCCESS;
      ret = SVK_STATUS_SUCCESS;
    }

  } catch (const boost::property_tree::ptree_error &e) {
    svk_logger(RAS_LOGGER, level_E::ERROR, e.what());
  }

  return ret;
}

inline svk_status execute_mock_logic_async(svk_logic_cmd *pass_thru,
                                           svk_postprocess_fn *postprocess_fn) {
  return SVK_STATUS_SUCCESS;
}

inline svk_status cleanup_mock_logic_module(void *param) {
    // Kill rasdaemon process
    int ret;
    ret = system("pkill -9 -f rasdaemon > /dev/null");
    if (ret < 0)
      return  SVK_STATUS_FAIL;

  return SVK_STATUS_SUCCESS;
}

inline svk_status configure_mock_logic(const std::string slat_logic_conf_file) {
  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status initialize_logic_module(void *init_param) {
  if (startup((const char *)init_param))
    return SVK_STATUS_FAIL;
  else {
    // Kill all existing rasdaemon processes
    int ret;
    ret = system("pkill -9 -f rasdaemon > /dev/null");
    if (ret < 0)
      return  SVK_STATUS_FAIL;

    // Start a new rasdaemon process
    ret = system("rasdaemon -r > /dev/null 2>&1");
    if (ret < 0)
      return  SVK_STATUS_FAIL;

    return SVK_STATUS_SUCCESS;
  }
}

extern "C" svk_status get_supported_logic_details(
    svk_logic_module_details *details) {
  strncpy(details->feature_name, "ras", sizeof(details->feature_name) - 1);
  strncpy(details->logic_module_name, "mock",
          sizeof(details->logic_module_name) - 1);

  details->execute_logic_sync = &execute_mock_logic_sync;
  details->execute_logic_async = &execute_mock_logic_async;
  details->cleanup_logic_module = &cleanup_mock_logic_module;

  return SVK_STATUS_SUCCESS;
}
