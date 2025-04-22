#ifndef LIBMOCK
#define LIBMOCK

#include <numa.h>
#include <rapidjson/document.h>
#include <rapidjson/error/en.h>
#include <rapidjson/error/error.h>
#include <rapidjson/filereadstream.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>
#include <stdio.h>
#include <syslog.h>

#include <string>

#define STR(x) #x
#define CONFIG_FILE "config/mock_config.json"

// Enum definition for errors
// These errors are listed for failure for each library, system API
// or functions defined in this module. These are returned using the return
// value of those calls
enum {
  OK,
  USAGE_ERR,
  CONFIG_FILE_NOT_AVAILABLE_ERR,
  INVALID_CONFIG_FILE_ERR,
  CONFIG_FILE_PARSE_ERR,
  GREP_CXL_MISSING_ERR,
  GREP_ACPI_SRAT_MISSING_ERR,
  REGEX_IOMEM_MISSING_ERR,
  REGEX_ADDR_RANGE_MISSING_ERR,
  INIT_ERR,
  NUMA_NOT_AVAILABLE_ERR,
  OPT_ERR,
  NUMA_MAX_NODE_ERR,
  INVALID_NUMA_INDEX_ERR,
  NOT_CXL_NODE_ERR,
  NUMA_ALLOCATE_CPUMASK_ERR,
  NUMA_NODE_TO_CPUS_ERR,
  NOT_CPULESS_NODE_ERR,
  ADDRESS_NOT_OF_NUMA_NODE_ERR,
  IOMEM_NOT_MATCHING_ACPI_SRAT_ERR,
  MCE_INJECT_TEMPLARE_STRING_MISSING_ERR,
  RASDAEMON_EXEC_COMMAND_MISSING_ERR,
  NUMA_NODE_PID_ERR,
  GET_STACK_VIRTUAL_ADDRESS_ERR,
  RASMCCTL_ERROR_ADDRESSES_MISSING_ERR,
  REGISTER_FUNCTION_ERR,
  GET_ERROR_COUNT_VALIDATION_ERR,
  INPUT_JSON_PARSE_ERR,
  INVALID_INPUT_ERR,
  UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR,
  CMD_EXEC_ERR,
  END
};

// Error string for errors using enums
const char* err_str[] = {STR(OK),
                         STR(USAGE_ERR),
                         STR(CONFIG_FILE_NOT_AVAILABLE_ERR),
                         STR(INVALID_CONFIG_FILE_ERR),
                         STR(CONFIG_FILE_PARSE_ERR),
                         STR(GREP_CXL_MISSING_ERR),
                         STR(GREP_ACPI_SRAT_MISSING_ERR),
                         STR(REGEX_IOMEM_MISSING_ERR),
                         STR(REGEX_ADDR_RANGE_MISSING_ERR),
                         STR(INIT_ERR),
                         STR(NUMA_NOT_AVAILABLE_ERR),
                         STR(OPT_ERR),
                         STR(NUMA_MAX_NODE_ERR),
                         STR(INVALID_NUMA_INDEX_ERR),
                         STR(NOT_CXL_NODE_ERR),
                         STR(NUMA_ALLOCATE_CPUMASK_ERR),
                         STR(NUMA_NODE_TO_CPUS_ERR),
                         STR(NOT_CPULESS_NODE_ERR),
                         STR(ADDRESS_NOT_OF_NUMA_NODE_ERR),
                         STR(IOMEM_NOT_MATCHING_ACPI_SRAT_ERR),
                         STR(MCE_INJECT_TEMPLARE_STRING_MISSING_ERR),
                         STR(RASDAEMON_EXEC_COMMAND_MISSING_ERR),
                         STR(NUMA_NODE_PID_ERR),
                         STR(GET_STACK_VIRTUAL_ADDRESS_ERR),
                         STR(RASMCCTL_ERROR_ADDRESSES_MISSING_ERR),
                         STR(REGISTER_FUNCTION_ERR),
                         STR(GET_ERROR_COUNT_VALIDATION_ERR),
                         STR(INPUT_JSON_PARSE_ERR),
                         STR(INVALID_INPUT_ERR),
                         STR(UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR),
                         STR(CMD_EXEC_ERR),
                         STR(END)};

using namespace std;

// Initialization function
int startup(char const* cfg);

// Generic request function using a JSON string
string processRequest(string& request);

// getErrorCount API
string getErrorCount(const string& device, const string& type);

// Validate device string ID before calling getErrorCount
int getErrorCount_validate(const string& device);

// Validate device NUMA node index
int verify_node(const int& node_index);

// Validate the CXL NUMA device physical address range allocation
int determine_physical_address_range(string&, const bool, string&);

// Get the physical address allocation of any NUMA device
int get_numa_node_address_range(const int& node_index, const bool cxl_node,
                                string& phy_addr_range);

// Find the total number of lines in ras-mc-ctl output that has address
// between the limits of provided address range
string calculateErrorCount(string& res, string& addr_range);

// Validate the provided JSON string string to be a proper for processing
int validate_config(const string& text);

// Get JSON config file size
long get_file_size(string filename);

// Get the address range valid for a partucular NUMA device in ras-mc-ctl
// output
string find_address_range_from_rasmcctl(string& dev, string& type);

#endif

