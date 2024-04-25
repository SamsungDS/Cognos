#include "sample_feature.h"

#include <string.h>

#include <iostream>
#include <memory>

using namespace std;

extern "C" int initialize(void *details) {
  std::cout << "sample feature init called" << std::endl;

  return 0;
}

// Emulating power throttle
extern "C" int get_supported_feature_list(feature_id *feature,
                                          char *feature_names) {
  *feature = feature_id::POWER_THROTTLE;
  std::cout << "sample feature get_supported_feature_list called" << std::endl;

  return 0;
}

extern "C" int is_license_valid(void *) {
  std::cout << "sample feature is_license_valid called" << std::endl;

  return 0;
}

// Assuming that input and output buffers contain strings
extern "C" int execute_sync(svk_pass_thru_cmd *cmd, svk_input *input,
                            svk_output *output) {
  char *buf;
  int status = -1;
  buf = (char *)input->input_buffer;
  printf("Input buffer: %s\n", buf);

  printf("sample feature execute_sync called\n");
  char *output_buf = (char *)output->output_buffer;
  if (strstr(buf, "SampleFeatureFailure")) {
    output->len =
        snprintf(output_buf, output->len, "SampleFeature: Failed to run");
    output->status = SVK_STATUS_FAIL;
  } else {
    output->len = snprintf(output_buf, output->len, "sample_key=value");
    output->status = SVK_STATUS_SUCCESS;
    status = 0;
  }
  return status;
}

extern "C" int execute_async(svk_pass_thru_cmd *pass_thru, svk_input *input,
                             svk_postprocess_fn *postprocess_fn) {
  std::cout << "sample feature execute_async called" << std::endl;

  return 0;
}

extern "C" int clean_up(void *) {
  std::cout << "sample feature clean_up called" << std::endl;

  return 0;
}
