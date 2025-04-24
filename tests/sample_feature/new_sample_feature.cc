#include <string.h>

#include <iostream>
#include <memory>

#include "sample_feature.h"

using namespace std;

extern "C" svk_status initialize(void *details) {
  std::cout << "new_sample_feature init called" << std::endl;

  return SVK_STATUS_SUCCESS;
}

// Emulating power throttle
extern "C" svk_status get_supported_feature_list(feature_id *feature,
                                                 char *feature_names) {
  std::cout
      << "new_sample_feature get_supported_feature_list called, returning "
         "failure to support new feature loading using feature_name"
      << std::endl;

  return SVK_STATUS_FAIL;
}

extern "C" svk_status is_license_valid(void *) {
  std::cout << "new_sample_feature is_license_valid called" << std::endl;

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status configure_device_if_any(void *config_details,
                                              svk_device_ctx *device_handles,
                                              uint64_t length, void *resp) {
  std::cout << "new_sample_feature configure_device called" << std::endl;

  return SVK_STATUS_SUCCESS;
}

// Assuming that input and output buffers contain strings
extern "C" svk_status execute_sync(svk_pass_thru_cmd *cmd, svk_input *input,
                                   svk_output *output) {
  char *buf;
  svk_status status = SVK_STATUS_FAIL;
  buf = (char *)input->input_buffer;
  printf("Input buffer: %s\n", buf);

  printf("new_sample_feature execute_sync called\n");
  char *output_buf = (char *)output->output_buffer;
  if (strstr(buf, "SampleFeatureFailure")) {
    output->len =
        snprintf(output_buf, output->len, "SampleFeature: Failed to run");
    output->status = SVK_STATUS_FAIL;
    return SVK_STATUS_FAIL;
  }

  output->len =
      snprintf(output_buf, output->len, "{\"output_key\":\"output_value\"}");
  output->status = SVK_STATUS_SUCCESS;
  status = SVK_STATUS_SUCCESS;

  return status;
}

extern "C" svk_status execute_async(svk_pass_thru_cmd *pass_thru,
                                    svk_postprocess_fn *postprocess_fn) {
  std::cout << "new_sample_feature execute_async called" << std::endl;

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status clean_up(void *) {
  std::cout << "new_sample_feature clean_up called" << std::endl;

  return SVK_STATUS_SUCCESS;
}
