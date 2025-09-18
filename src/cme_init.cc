#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <sys/stat.h>
#include <tuple>
#include <unordered_map>
#include <vector>
#include <string.h>
#include "framework_downstream.h"
#include "yaml-cpp/yaml.h"
#include "cme_global.h"
#include "cme_utils.h"
#include "cme_logger.h"

/*
extern "C"{
#include "jansson.h"
}
*/

#define CME_FEATURE_ID 0xDEADBEEF

constexpr char DELIMITER[] = ",";

using namespace std;

// function pointers for the commands
typedef std::string (*CommandFunc) (const std::string &);

// Global cme object
cme_global cme_global_obj;

/**
 * @brief init cme functionality
 */
int 
cme_init ()
{
        int rc = cme_global_obj.read_cme_config_json(CME_CONFIG_FILE);
        if (rc !=0)
        {
                CME_ERR("read_cme_config_json failed for : ");
                return -EINVAL;
        }

        rc = cme_global_obj.cme_discovery();
        if (rc !=0)
        {
                CME_ERR("cme_discovery failed");
                return -EINVAL;
        }
	rc = cme_global_obj.initialize();
        if (rc !=0)
        {
                CME_ERR("cme_initialize failed");
                return -EINVAL;
        }
        return 0;
}

/**
 * @brief de_init cme functionality
 */
int 
cme_clean_up ()
{

 	int rc = cme_global_obj.clean_up();
        if (rc !=0)
        {
                CME_ERR("de_init failed");
                return -EINVAL;
        }
        return 0;
}


/**
 * @brief init function
 * @details This function will be triggered first for any requests from client
 * side.
 */
int
init_cme_plugin ()
{
        CME_LOG("INFO", "invoked init_cme_plugin");
        int rc = cme_init();
        return rc;
}

/**
 * ########################################
 * # Start SVK Core Framework Integration #
 * ########################################
 */

/**
 * @brief Initialize individual feature module
 *
 * This will be called when individual feature module will be loaded by
 * framework.
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status
initialize (void *)
{
        CME_LOG("INFO", "initialize function called");

        if (init_cme_plugin () == 0)
        {
                return SVK_STATUS_SUCCESS;
        }
        else
        {
                return SVK_STATUS_FAIL;
        }
}


/*
 * Feature modules set feature_id to the *feat_id pointer if
 * it isn't set already.
 * SVK command framework will call this function to get the feature names
 * this feature module will support.
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status
get_supported_feature_list (feature_id *feat_id, char *feature_name)
{
        CME_LOG("INFO", "get_supported_feature_list function called");
        return SVK_STATUS_FAIL;
}

/**
 * @brief Check if license is valid
 *
 * Every request needs to validate if license is valid before moving on
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status
is_license_valid (void *)
{
        CME_LOG("INFO", "is_license_valid function called");
        return SVK_STATUS_SUCCESS;
}

/**
 * @brief API for feature modules that need to access/initialize a device
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status
configure_device_if_any (void *, svk_device_ctx *, uint64_t length, void *)
{
        CME_LOG("INFO", "configure_device_if_any function called");
        return SVK_STATUS_SUCCESS;
}



/**
 * @brief Exact feature execution logic will be implemented here
 *
 * @param pass_thru svk passthrough for command info communication from top
 * level
 * @param input     input buffer struct
 * @param result    output buffer struct
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status
execute_sync (svk_pass_thru_cmd *, svk_input *input, svk_output *output)
{
        CME_LOG("INFO", "execute_sync function called");
        std::string input_str (reinterpret_cast<char *> (input->input_buffer),
                                input->len);
        CME_LOG("INFO", "Input command received = ", input_str);
	std::string result;
  
        try  
        {
                result = cme_global_obj.cme_command_handler(input_str);
	}
        catch (const std::exception &e)
        {
                CME_ERR("cme_command_handler. Error -> ", e.what ());
                return SVK_STATUS_FAIL;
        }

        output->output_buffer
        = reinterpret_cast<uint8_t *> (strdup (result.c_str ()));
        output->len = result.size ();
        output->status = SVK_STATUS_SUCCESS;
        return SVK_STATUS_SUCCESS;
}

/**
 * @brief Feature module async execute implementation.
 *
 * @param pass_thru       svk passthrough for command info communication from
 * top level
 * @param input           input buffer struct
 * @param postprocess_fn  struct containing pointers for async IO, such as
 * callback, IO identifier, and output buffer
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status
execute_async (svk_pass_thru_cmd *, svk_postprocess_fn *)
{
  CME_LOG("INFO", "execute_async function called");
  return SVK_STATUS_FAIL;
}

/**
 * @brief Usual cleanup before exit
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status
clean_up (void *)
{
  CME_LOG("INFO", "clean_up function called");
  cme_clean_up ();
  return SVK_STATUS_FAIL;
}

/**
 * ######################################
 * # END SVK Core Framework Integration #
 * ######################################
 */
