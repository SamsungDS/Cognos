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
  string regex_iomem;
  string regex_addr_range;
  string mce_inject_template_string;
  string rasdaemon_exec_command;
  string ras_mc_ctl_error_addresses;
};

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
  int ret = 0;
  string res;
  FILE *pipe = popen(cmd.c_str(), "r");

  if (!pipe) {
    return (string(err_str[CMD_EXEC_ERR]) + " Error opening pipe " +
            strerror(errno));
  }

  char buffer[128];
  while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
    res += buffer;
  }

  int status = pclose(pipe);
  if ((status == -1) || (WIFEXITED(status)) || (WIFSIGNALED(status))) {
    ret = CMD_EXEC_ERR;
    res = string(err_str[ret]) + " Error closing pipe " + strerror(errno);
    return res;
  }
  return res;
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
      res = m[1].str();
      remove_substr(res, "0x");
      phy_addr_range += (res + " ");
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
  return ret;
}

/***
 * Initialization to start a log file and read magic strings from
 * config.json file
 */
int init(char const *cfg = CONFIG_FILE) {
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
int getErrorCount_validate(const string &dev) {
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

// Creating JSON string response for getErrorCount
string createResponse(const char *status, string &response) {
  Document document;
  document.SetObject();

  Document::AllocatorType &allocator = document.GetAllocator();

  // Allocating memory to add status
  Value stat;
  stat.SetString(status, allocator);
  document.AddMember("Status", stat, allocator);

  // Allocating memory to add response
  Value resp;
  resp.SetString(response.c_str(), allocator);
  document.AddMember("Response", resp, allocator);

  StringBuffer buffer;
  Writer<StringBuffer> writer(buffer);
  document.Accept(writer);

  string jsonString = buffer.GetString();

  return jsonString;
}

// Get the error count using ras-mc-ctl output
string calculateErrorCount(string &res, string &addr_range) {
  int ret = 0;
  string response, retresp, tok;
  string delim = "-";
  size_t dpos = addr_range.find(delim);

  if ((res.size() == 0) || (addr_range.size() == 0) || (dpos == string::npos)) {
    ret = UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR;
    response = "Empty or Invalid address range detected";
    retresp = createResponse(err_str[ret], response);
    return retresp;
  }

  string t1 = addr_range.substr(0, dpos);
  string t2 = addr_range.substr(dpos + 1, addr_range.size() - 1);
  long low_addr = stol(t1, 0, 16);
  long high_addr = stol(t2, 0, 16);

  long count = 0, val;
  stringstream ss(res);
  while (getline(ss, tok, '\n')) {
    if (tok.empty()) {
      continue;
    } else {
      val = stol(tok, 0, 16);
      if (val >= low_addr && val <= high_addr) {
        ++count;
      }
    }
  }
  response.assign(to_string(count));
  retresp = createResponse(err_str[ret], response);
  return retresp;
}

// The implementation of getErrorCount
// Counts the physical addresses valid for the provided node index
string getErrorCount(const string &dev, const string &type) {
  int ret = 0, noden = -1;
  string status, response = "", retresp, addr_range, res = "";
  bool cxl = false;

  ret = getErrorCount_validate(dev);
  if (ret != 0) {
    response = "Error during validation of device ID: " + dev;
    retresp = createResponse(err_str[ret], response);
    return retresp;
  } else {
    noden = stoi(dev);
    ret = get_numa_node_address_range(noden, cxl, addr_range);
    if (ret != 0) {
      response = "Error getting address range of device ID: " + dev;
      retresp = createResponse(err_str[ret], response);
      return retresp;
    }

    string cmd = cf.ras_mc_ctl_error_addresses;
    if (!cmd.empty()) res = cmd_exec(cmd);

    return calculateErrorCount(res, addr_range);
  }
}

// Invoked during initialization
int startup(char const *cfg = CONFIG_FILE) { return init(cfg); }

// Process the request using the request string
string processRequest(string &request) {
  int ret = 0;
  // Create a rapidjson document
  Document document;
  string cmd_str, cmd, device_str, device, type_str, type, res, estring;

  // Parse the JSON string
  document.Parse(request.c_str());
  ret = document.HasParseError();
  if (ret != 0) {
    ret = INPUT_JSON_PARSE_ERR;
    estring = GetParseError_En(document.GetParseError());
    res = createResponse(err_str[INPUT_JSON_PARSE_ERR], estring);
  } else {
    // Check if the document is an object
    if (document.IsObject()) {
      // Get the object
      const auto &object = document.GetObject();

      // Iterate through the object's members
      for (auto &member : object) {
        const Value &name = member.name;
        if (name.IsString() && (name == "command")) {
          cmd_str = name.GetString();
          const Value &value = member.value;
          if (value.IsString()) {
            cmd = value.GetString();
          }
        } else if (name.IsString() && (name == "device")) {
          device_str = name.GetString();
          const Value &value = member.value;
          if (value.IsNumber()) {
            device = to_string(value.GetInt());
          } else if (value.IsString()) {
            device = value.GetString();
          }
        } else if (name.IsString() && (name == "type")) {
          type_str = name.GetString();
          const Value &value = member.value;
          if (value.IsString()) {
            type = value.GetString();
          }
        }
      }

      if ((cmd == "getErrorCount") && (device_str == "device") &&
          ((type == "correctable") || (type == "uncorrectable"))) {
        res = getErrorCount(device, type);
      } else {
        ret = INVALID_INPUT_ERR;
        estring = "Invalid/Missing Key Name and/or Invalid Value Provided";
        res = createResponse(err_str[INVALID_INPUT_ERR], estring);
      }
    }
  }
  return res;
}
