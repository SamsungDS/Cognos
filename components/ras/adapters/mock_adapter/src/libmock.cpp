// Source code for Mock Adapter API
#include "libmock.h"

#include <numa.h>
#include <numaif.h>
#include <rapidjson/document.h>
#include <rapidjson/error/en.h>
#include <rapidjson/error/error.h>
#include <rapidjson/filereadstream.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <syslog.h>
#include <unistd.h>

#include <array>
#include <atomic>
#include <climits>
#include <cstring>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <regex>
#include <sstream>

#include "ras.hpp"

#define BLOCK_SIZE 4096
#define MAX_ERR_SIZE 50

using namespace std;
using namespace rapidjson;

// Configuration global variables as defined in config.json
struct Config {
  string grep_CXL;
  string grep_acpi_srat;
  string grep_numa_nodes;
  string regex_iomem;
  string regex_addr_range;
  string mce_inject_template_string;
  string rasdaemon_exec_command;
  string ras_mc_ctl_error_addresses;
  string ras_mc_ctl_health_status_command;
};

const std::string mock_adapter_default_config = R"(
{
  "grep_CXL": "cat /proc/iomem|grep CXL",
  "grep_acpi_srat": "journalctl -k|grep -i acpi|grep -i srat",
  "grep_numa_nodes": "journalctl -k|grep -i acpi|grep -i srat|grep -oP '(?<=Node).* (?=PXM)'|uniq",
  "regex_iomem": "^[\\s]*[0-9a-z]+-[0-9a-z]+[\\s]*:[\\s]*CXL[\\s]*Window[\\s]*[0-9]+$",
  "regex_addr_range": ".*mem[\\s]*([0-9a-z]+-[0-9a-z]+).*",
  "mce_inject_template_string": "CPU {cpu} BANK 1\nSTATUS CORRECTED\nADDR {addr}\n",
  "rasdaemon_exec_command": "/usr/local/svk/feature_modules/ras/adapters/mock/tools/usr/local/sbin/rasdaemon -f -r /dev/null 2>&1 > ",
  "ras_mc_ctl_error_addresses": "/usr/local/svk/feature_modules/ras/adapters/mock/tools/usr/local/sbin/ras-mc-ctl --errors|grep -Po '(?<=addr=)[^,]*|No MCE errors'"
}
)";

// Instantiation of global vars to be used as key-value pairs
Config cf;
ostringstream os(ostringstream::ate), emp;

// trim from left
inline string &ltrim(std::string &s, const char *t = " \t\n\r\f\v") {
  s.erase(0, s.find_first_not_of(t));
  return s;
}

// trim from right
inline string &rtrim(std::string &s, const char *t = " \t\n\r\f\v") {
  s.erase(s.find_last_not_of(t) + 1);
  return s;
}

// trim from left & right
inline string &trim(std::string &s, const char *t = " \t\n\r\f\v") {
  return ltrim(rtrim(s, t), t);
}

// Execute a command using command-line string using popen/pclose
string cmd_exec(string &cmd) {
  array<char, 128> buffer;
  string result;
  unique_ptr<FILE, void (*)(FILE *)> pipe(
      popen(cmd.c_str(), "r"), [](FILE *f) -> void { ignore = pclose(f); });
  if (!pipe) {
    throw std::runtime_error("popen() failed!");
  }
  while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe.get()) !=
         nullptr) {
    result += buffer.data();
  }
  return result;
}

// remove substring
inline void remove_substr(string &s, const string &p) {
  string::size_type n = p.length();
  for (string::size_type i = s.find(p); i != string::npos; i = s.find(p))
    s.erase(i, n);
}

// Verify that the user-provided node is a valid NUMA node
int verify_node(const int &node_index) {
  int ret = 0;
  int max_node = numa_max_node();

  if ((node_index > max_node) || (node_index < 0)) {
    return INVALID_NUMA_INDEX_ERR;
  }

  return ret;
}

// Find the physical address range using kernel log
int determine_physical_address_range(const string &out, const bool cxl_node,
                                     string &phy_addr_range) {
  int ret = 0;
  stringstream ss(out);
  string tok, res, regex_addr_range = cf.regex_addr_range;
  regex regex_acpi_srat(regex_addr_range);
  stack<string> st;

  // Find the appropriate entries mentioned in kernel log output
  while (getline(ss, tok, '\n')) {
    st.push(tok);
  }
  tok.clear();

  while (!st.empty()) {
    smatch m;
    tok = st.top();
    st.pop();
    if (regex_match(tok, m, regex_acpi_srat)) {
      if (cxl_node == false) {
        res = m[1].str();
        remove_substr(res, "0x");
        phy_addr_range += (res + " ");
      }
    }
  }

  if (phy_addr_range.empty()) {
    ret = UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR;
  }
  return ret;
}

// Use kernel output to get physical address allocation for NUMA node
int get_numa_node_address_range(const int &node_index, const bool cxl_node,
                                string &phy_addr_range) {
  int ret = 0;
  // Creating the command-line using the provided node index
  string in = cf.grep_acpi_srat +
              string("|grep \"Node " + to_string(node_index) + string("\""));

  // Execute the command-line formed from above
  string out = "";
  if (!in.empty()) out = cmd_exec(in);
  ret = determine_physical_address_range(out, cxl_node, phy_addr_range);
  return ret;
}

// Use kernel log (journalctl) to get all the registered NUMA nodes
int get_numa_nodes(Response &out) {
  int ret = 0;

  // Creating command-line string to get all numa nodes
  string in = cf.grep_numa_nodes;

  // Execute the command-line from above
  out.return_value = "";
  if (!in.empty()) out.return_value = cmd_exec(in);

  return ret;
}

// Get file size of config.json
long get_file_size(std::string filename) {
  struct stat stat_buf;
  int rc = stat(filename.c_str(), &stat_buf);
  return rc == 0 ? stat_buf.st_size : -1;
}

// Determine the VFS block size
inline int block_size() {
  int blk_size = BLOCK_SIZE;
  struct statvfs vfs_stat;
  if (statvfs("/", &vfs_stat) == 0) {
    blk_size = vfs_stat.f_bsize;
  }
  return blk_size;
}

// Parse config.json and validate key-value items
int validate_config(const string &str) {
  int ret = 0;
  Document data;
  if (data.Parse<0>(str.c_str()).HasParseError()) {
    os.swap(emp);
    os << "Detected parsing error: " << data.GetParseError()
       << ". Error (offset " << data.GetErrorOffset()
       << "): " << GetParseError_En(data.GetParseError()) << endl;
    svk_logger(RAS_LOGGER, level_E::ERROR, os.str().c_str());
    return CONFIG_FILE_PARSE_ERR;
  }

  if (data.HasMember("grep_CXL") && data["grep_CXL"].IsString()) {
    cf.grep_CXL = data["grep_CXL"].GetString();
    os.swap(emp);
    os << "grep_CXL: " << cf.grep_CXL.c_str() << endl;
    svk_logger(RAS_LOGGER, level_E::DEBUG, os.str().c_str());
  } else {
    return GREP_CXL_MISSING_ERR;
  }

  if (data.HasMember("grep_acpi_srat") && data["grep_acpi_srat"].IsString()) {
    cf.grep_acpi_srat = data["grep_acpi_srat"].GetString();
    os.swap(emp);
    os << "grep_acpi_srat: " << cf.grep_acpi_srat.c_str() << endl;
    svk_logger(RAS_LOGGER, level_E::DEBUG, os.str().c_str());
  } else {
    return GREP_ACPI_SRAT_MISSING_ERR;
  }

  if (data.HasMember("regex_iomem") && data["regex_iomem"].IsString()) {
    cf.regex_iomem = data["regex_iomem"].GetString();
    os.swap(emp);
    os << "reg_iomem: " << cf.regex_iomem.c_str() << endl;
    svk_logger(RAS_LOGGER, level_E::DEBUG, os.str().c_str());
  } else {
    return REGEX_IOMEM_MISSING_ERR;
  }

  if (data.HasMember("regex_addr_range") &&
      data["regex_addr_range"].IsString()) {
    cf.regex_addr_range = data["regex_addr_range"].GetString();
    os.swap(emp);
    os << "regex_addr_range: " << cf.regex_addr_range.c_str() << endl;
    svk_logger(RAS_LOGGER, level_E::DEBUG, os.str().c_str());
  } else {
    return REGEX_ADDR_RANGE_MISSING_ERR;
  }

  if (data.HasMember("rasdaemon_exec_command") &&
      data["rasdaemon_exec_command"].IsString()) {
    cf.rasdaemon_exec_command = data["rasdaemon_exec_command"].GetString();
    os.swap(emp);
    os << "rasdaemon_exec_command: " << cf.rasdaemon_exec_command.c_str()
       << endl;
    svk_logger(RAS_LOGGER, level_E::DEBUG, os.str().c_str());
  } else {
    return RASDAEMON_EXEC_COMMAND_MISSING_ERR;
  }

  if (data.HasMember("ras_mc_ctl_error_addresses") &&
      data["ras_mc_ctl_error_addresses"].IsString()) {
    cf.ras_mc_ctl_error_addresses =
        data["ras_mc_ctl_error_addresses"].GetString();
    os.swap(emp);
    os << "ras_mc_ctl_error_addresses: "
       << cf.ras_mc_ctl_error_addresses.c_str() << endl;
    svk_logger(RAS_LOGGER, level_E::DEBUG, os.str().c_str());
  } else {
    return RASMCCTL_ERROR_ADDRESSES_MISSING_ERR;
  }

  if (data.HasMember("grep_numa_nodes") && data["grep_numa_nodes"].IsString()) {
    cf.grep_numa_nodes = data["grep_numa_nodes"].GetString();
    os.swap(emp);
    os << "grep_numa_nodes: " << cf.grep_numa_nodes.c_str() << endl;
    svk_logger(RAS_LOGGER, level_E::DEBUG, os.str().c_str());
  } else {
    return GREP_NUMA_NODES_MISSING_ERR;
  }

  return ret;
}

/***
 * Initialization to start a log file and read magic strings from
 * config.json file
 */
int init_from_file(char const *cfg = nullptr) {
  int ret = 0;
  FILE *file;

  os.swap(emp);
  os << "Program started by User " << getuid() << endl;
  svk_logger(RAS_LOGGER, level_E::NOTICE, os.str().c_str());

  // Open config.json file for reading
  char actualpath[PATH_MAX + 1], *ptr = NULL;
  ptr = realpath(cfg, actualpath);

  if (ptr == NULL) {
    return CONFIG_FILE_NOT_AVAILABLE_ERR;
  }
  os.swap(emp);
  os << "Full path of " << cfg << ": " << actualpath << endl;
  svk_logger(RAS_LOGGER, level_E::DEBUG, os.str().c_str());

  long sz = get_file_size(cfg);
  if (sz <= 0) {
    return INVALID_CONFIG_FILE_ERR;
  }

  char readBuffer[sz + 1];
  file = fopen(cfg, "r");
  if (file != nullptr) {
    os.swap(emp);
    os << "Configuration file opened: " << cfg << endl;
    svk_logger(RAS_LOGGER, level_E::DEBUG, os.str().c_str());
    Document data;
    FileReadStream is(file, readBuffer, sizeof(readBuffer));
    fclose(file);
    ret = validate_config(readBuffer);
  }

  return ret;
}

// Validate the device string
int device_validate(const string &dev) {
  int ret = 0, noden = -1;
  if (dev.empty()) return INVALID_NUMA_INDEX_ERR;

  for (size_t i = 0; i < dev.size(); ++i) {
    if (!isdigit(dev[i]) || (isspace(dev[i]))) {
      return INVALID_NUMA_INDEX_ERR;
    }
  }
  noden = strtol(dev.c_str(), NULL, 0);
  if (noden < 0) {
    return INVALID_NUMA_INDEX_ERR;
  }

  ret = verify_node(stoi(dev));

  return ret;
}

// Creating JSON string response
string createResponse(const string &device, const string &error_type,
                      const char *status, const Response &response) {
  Document document;
  document.SetObject();

  Document::AllocatorType &allocator = document.GetAllocator();

  // Adding object for "getErrorCount/getHealthStatus/getDeviceList"
  Value request_function(kObjectType);

  // Adding device name
  if ((response.function_name == "getErrorCount") ||
      (response.function_name == "getHealthStatus")) {
    Value dev(kStringType);
    dev.SetString(device.c_str(), allocator);
    request_function.AddMember("device", dev, allocator);
  }

  // Adding error type
  if (response.function_name == "getErrorCount") {
    Value etype(kStringType);
    etype.SetString(error_type.c_str(), allocator);
    request_function.AddMember("errorType", etype, allocator);
  }

  // Adding result details
  Value result(kObjectType);

  // Adding success or fail status
  if (strcmp(status, "OK") == 0) {
    result.AddMember("commandSuccessful", true, allocator);
    if (response.function_name == "getErrorCount")
      result.AddMember("errorCount", stol(response.return_value), allocator);
    else if (response.function_name == "getHealthStatus") {
      long val = stol(response.return_value);
      if (val < HEALTH_DECIDER_VALUE)
        result.AddMember("healthStatus", true, allocator);
      else
        result.AddMember("healthStatus", false, allocator);
    } else if (response.function_name == "getDeviceList") {
      Value devlistarray(kArrayType);
      char *pch;
      pch = strtok((char *)response.return_value.c_str(), " \n");
      while (pch != NULL) {
        Value stringValue;
        stringValue.SetString(pch,
                              static_cast<rapidjson::SizeType>(
                                  strnlen(pch, response.return_value.length())),
                              allocator);
        devlistarray.PushBack(stringValue, allocator);
        pch = strtok(NULL, " \n");
      }
      result.AddMember("deviceList", devlistarray, allocator);
    }

  } else {
    result.AddMember("commandSuccessful", false, allocator);
  }

  // Adding request function under command response
  if (response.function_name == "getErrorCount")
    document.AddMember("command_response", "getErrorCount", allocator);
  else if (response.function_name == "getHealthStatus")
    document.AddMember("command_response", "getHealthStatus", allocator);
  else if (response.function_name == "getDeviceList")
    document.AddMember("command_response", "getDeviceList", allocator);
  else
    document.AddMember("command_response", "None", allocator);

  document.AddMember("command_params", request_function, allocator);
  // Adding result to request_function
  document.AddMember("result", result, allocator);

  StringBuffer buffer;
  Writer<StringBuffer> writer(buffer);
  document.Accept(writer);

  string jsonString = buffer.GetString();

  return jsonString;
}

// Get the error count using ras-mc-ctl output
int calculateErrorCount(string &res, string &addr_range, Response &out) {
  int ret = 0;
  string response, retresp, tok;
  string delim = "-";
  size_t dpos = addr_range.find(delim);

  if ((res.size() == 0) || (addr_range.size() == 0) || (dpos == string::npos)) {
    ret = UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR;
    response = "Empty or Invalid address range detected";
    svk_logger(RAS_LOGGER, level_E::ERROR, response.c_str());
    return ret;
  }

  string t1 = addr_range.substr(0, dpos);
  string t2 = addr_range.substr(dpos + 1, addr_range.size() - 1);
  long low_addr = stol(t1, 0, 16);
  long high_addr = stol(t2, 0, 16);

  long count = 0, val;
  stringstream ss(res);
  while (getline(ss, tok, '\n')) {
    if (tok.empty() || (tok == NO_MCE_ERRORS)) {
      continue;
    } else if (tok.compare(0, 2, "0x") == 0 && tok.size() > 2 &&
               tok.find_first_not_of("0123456789abcdefABCDEF", 2) ==
                   std::string::npos) {
      val = stol(tok, 0, 16);
      if (val >= low_addr && val <= high_addr) {
        ++count;
      }
    } else {
      ret = RASMCCTL_OUTPUT_ERR;
      response = "Error in ras-mc-ctl output";
      svk_logger(RAS_LOGGER, level_E::ERROR, response.c_str());
      return ret;
    }
  }

  // Adding the error count to Response output field
  out.return_value.assign(to_string(count));

  return ret;
}

// The implementation of getErrorCount
// Counts the physical addresses valid for the provided node index
int getErrorCount(const string &dev, const string &type, Response &out) {
  int ret = 0, noden = -1;
  string response = "", retresp, addr_range, res = "";
  bool cxl = false;

  ret = device_validate(dev);
  if (ret != 0) {
    response = "Error during validation of device ID: " + dev;
    out.response_details = response;
    retresp = createResponse(dev, type, err_str[ret], out);
    svk_logger(RAS_LOGGER, level_E::ERROR, retresp.c_str());
    return ret;
  } else {
    noden = stoi(dev);
    ret = get_numa_node_address_range(noden, cxl, addr_range);
    if (ret != 0) {
      response = "Error getting address range of device ID: " + dev;
      out.response_details = response;
      retresp = createResponse(dev, type, err_str[ret], out);
      svk_logger(RAS_LOGGER, level_E::ERROR, retresp.c_str());
      return ret;
    }

    string cmd = cf.ras_mc_ctl_error_addresses;
    if (!cmd.empty()) res = cmd_exec(cmd);

    return calculateErrorCount(res, addr_range, out);
  }
}

// The implementation of getHealthStatus leverages getErrorCount
int getHealthStatus(const string &dev, Response &out, const string &type) {
  return getErrorCount(dev, type, out);
}

// The implementation for getDeviceList
int getDeviceList(Response &out) {
  int ret = 0;
  ret = get_numa_nodes(out);

  return ret;
}

// Invoked during initialization
int startup(char const *cfg = nullptr) {
  if (cfg != nullptr) {
    return init_from_file(cfg);
  } else {
    return validate_config(mock_adapter_default_config);
  }
}

// Process the request using the request string
string processRequest(string &request) {
  int ret = 0;
  // Create a rapidjson document
  Document document;
  string cmd_str, cmd, device_str, device, type_str, type, res, estring, fname;

  // Parse the JSON string
  document.Parse(request.c_str());
  ret = document.HasParseError();
  if (ret != 0) {
    ret = INPUT_JSON_PARSE_ERR;
    estring = GetParseError_En(document.GetParseError());
    Response out = {.function_name = "processRequest"};
    out.response_details = estring;
    res = createResponse(device, type, err_str[ret], out);
  } else {
    // Check if the document is an object
    if (document.IsObject()) {
      if (document.HasMember("command_name") &&
          document["command_name"].IsString()) {
        fname = document["command_name"].GetString();
        cmd = fname.c_str();

        if (document.HasMember("command_params")) {
          const Value &f = document["command_params"];
          if (f.IsObject()) {
            for (auto &x : f.GetObject()) {
              if (x.name.IsString() && x.name == "device") {
                device_str = x.name.GetString();
                if (x.value.IsNumber()) {
                  device = to_string(x.value.GetInt());
                } else if (x.value.IsString()) {
                  device = x.value.GetString();
                }
              }
              if (x.name.IsString() && x.name == "errorType") {
                type_str = x.name.GetString();
                if (x.value.IsNumber()) {
                  type = to_string(x.value.GetInt());
                } else if (x.value.IsString()) {
                  type = x.value.GetString();
                }
              }
            }
          }
        }
      }
    }
  }

  Response out = {.function_name = cmd};
  if ((cmd == "getErrorCount") && (device_str == "device") &&
      ((type == "correctable") || (type == "uncorrectable"))) {
    ret = getErrorCount(device, type, out);
    res = createResponse(device, type, err_str[ret], out);
    svk_logger(RAS_LOGGER, level_E::INFO, res.c_str());

  } else if ((cmd == "getHealthStatus") && (device_str == "device")) {
    ret = getHealthStatus(device, out);
    res = createResponse(device, type, err_str[ret], out);
    svk_logger(RAS_LOGGER, level_E::INFO, res.c_str());

  } else if (cmd == "getDeviceList") {
    ret = getDeviceList(out);
    res = createResponse(device, type, err_str[ret], out);
    svk_logger(RAS_LOGGER, level_E::INFO, res.c_str());

  } else {
    ret = INVALID_INPUT_ERR;
    estring = res + ":Invalid/Missing Key Name and/or Invalid Value Provided";
    out.response_details = estring;
    res = createResponse(device, type, err_str[ret], out);
    svk_logger(RAS_LOGGER, level_E::ERROR, estring.c_str());
  }
  return res;
}
