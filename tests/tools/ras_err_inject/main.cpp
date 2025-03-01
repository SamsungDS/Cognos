#include <fcntl.h>
#include <getopt.h>
#include <numa.h>
#include <numaif.h>
#include <rapidjson/document.h>
#include <rapidjson/error/en.h>
#include <rapidjson/error/error.h>
#include <rapidjson/filereadstream.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <syslog.h>
#include <unistd.h>

#include <array>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <memory>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>

#define NUMA_ALLOCATION_SIZE 1024
#define CONFIG_FILE "config.json"
#define APP_LOG "svk_ras_einj.log"
#define ras_log(x, ...) syslog(x, ##__VA_ARGS__)

using namespace std;
using namespace rapidjson;

// Configuration global variables as defined in config.json
struct Config {
  string grep_CXL;
  string grep_acpi_srat;
  string regex_iomem;
  string regex_addr_range;
};

// Instantiation of global vars to be used as key-value pairs
Config cf;

// Struct derived from https://www.kernel.org/doc/Documentation/vm/pagemap.txt
typedef struct {
  uint64_t pfn : 55;
  unsigned int soft_dirty : 1;
  unsigned int file_page : 1;
  unsigned int swapped : 1;
  unsigned int present : 1;
} PagemapEntry;

// Enum definition for errors
enum {
  USAGE_ERR = 101,
  CONFIG_FILE_NOT_AVAILABLE_ERR,
  INVALID_CONFIG_FILE_SIZE_ERR,
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
  INVALID_PAGEMAP_ERR,
  PAGEMAP_GET_ERR,
  NUMA_ALLOCATE_CPUMASK_ERR,
  NUMA_NODE_TO_CPUS_ERR,
  NOT_CPULESS_NODE_ERR,
  NUMA_ALLOC_ON_NODE_ERR,
  FAILURE_TO_MAP_VIRTUAL_TO_PHYSICAL_MEM_ERR,
  ADDRESS_NOT_OF_NUMA_NODE_ERR,
  IOMEM_NOT_MATCHING_ACPI_SRAT_ERR
};

// Wrapper around syslog
// void ras_log(int pri, char *buf) { syslog(pri, "%s", buf); }

// Parse the pagemap entry for the given virtual address.
int pagemap_get_entry(PagemapEntry *entry, int pagemap_fd, uintptr_t vaddr) {
  if (vaddr == 0) return 1;

  size_t nread;
  ssize_t ret;
  uint64_t data;
  uintptr_t vpn;

  vpn = vaddr / sysconf(_SC_PAGE_SIZE);
  nread = 0;
  while (nread < sizeof(data)) {
    ret = pread(pagemap_fd, ((uint8_t *)&data) + nread, sizeof(data) - nread,
                vpn * sizeof(data) + nread);
    nread += ret;
    if (ret <= 0) {
      return 1;
    }
  }
  entry->pfn = data & (((uint64_t)1 << 55) - 1);
  entry->soft_dirty = (data >> 55) & 1;
  entry->file_page = (data >> 61) & 1;
  entry->swapped = (data >> 62) & 1;
  entry->present = (data >> 63) & 1;
  return 0;
}

// Convert the given virtual address to physical using /proc/PID/pagemap.
int virt_to_phys_user(uintptr_t *paddr, pid_t pid, uintptr_t vaddr) {
  char pagemap_file[BUFSIZ];
  int pagemap_fd;

  snprintf(pagemap_file, sizeof(pagemap_file), "/proc/%ju/pagemap",
           (uintmax_t)pid);
  pagemap_fd = open(pagemap_file, O_RDONLY);
  if (pagemap_fd < 0) {
    return INVALID_PAGEMAP_ERR;
  }
  PagemapEntry entry;
  if (pagemap_get_entry(&entry, pagemap_fd, vaddr)) {
    return PAGEMAP_GET_ERR;
  }
  close(pagemap_fd);
  *paddr =
      (entry.pfn * sysconf(_SC_PAGE_SIZE)) + (vaddr % sysconf(_SC_PAGE_SIZE));
  return 0;
}

// This function returns the NUMA node that a pointer address resides on.
int get_node(void *p) {
  int status[1];
  void *pa;
  unsigned long a;

  // round p down to the nearest page boundary
  a = (unsigned long)(p);
  a = a - (a % ((unsigned long)getpagesize()));
  pa = (void *)a;

  if (move_pages(0, 1, &pa, NULL, status, 0) != 0) {
    ras_log(LOG_CRIT, "Problem in %s line %d calling move_pages()", __FILE__,
            __LINE__);
    abort();
  }

  return (status[0]);
}

// Execute a command using popen/pclose
std::string cmd_exec(string &cmd) {
  std::array<char, 128> buffer;
  std::string result;
  std::unique_ptr<FILE, void (*)(FILE *)> pipe(
      popen(cmd.c_str(), "r"),
      [](FILE *f) -> void { std::ignore = pclose(f); });
  if (!pipe) {
    throw std::runtime_error("popen() failed!");
  }
  while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe.get()) !=
         nullptr) {
    result += buffer.data();
  }
  return result;
}

// trim from left
string &ltrim(std::string &s, const char *t = " \t\n\r\f\v") {
  s.erase(0, s.find_first_not_of(t));
  return s;
}

// trim from right
string &rtrim(std::string &s, const char *t = " \t\n\r\f\v") {
  s.erase(s.find_last_not_of(t) + 1);
  return s;
}

// trim from left & right
string &trim(std::string &s, const char *t = " \t\n\r\f\v") {
  return ltrim(rtrim(s, t), t);
}

// remove substring
void remove_substr(string &s, const string &p) {
  string::size_type n = p.length();
  for (string::size_type i = s.find(p); i != string::npos; i = s.find(p))
    s.erase(i, n);
}

void timestamp(char *buf) {
  chrono::system_clock::time_point now = std::chrono::system_clock::now();
  time_t currentTime = std::chrono::system_clock::to_time_t(now);
  chrono::milliseconds now2 =
      std::chrono::duration_cast<std::chrono::milliseconds>(
          now.time_since_epoch());
  struct tm currentLocalTime;
  localtime_r(&currentTime, &currentLocalTime);
  char timeBuffer[80];
  std::size_t charCount{
      std::strftime(timeBuffer, 80, "%D %T", &currentLocalTime)};

  if (charCount == 0)
    strcpy(buf, "");
  else
    sprintf(buf, "%s.%3ld", timeBuffer, now2.count() % 1000);
}

// Verify CPU-less NUMA node
int verify_zero_cpu_node(const int &node_index) {
  struct bitmask *cpus;
  int ret = 0;

  // Assigning bits for CPUs and evaluating
  cpus = numa_allocate_cpumask();
  if (!cpus) {
    ras_log(LOG_ERR, "Error reported by numa_allocate_cpumask()");
    ret = NUMA_ALLOCATE_CPUMASK_ERR;
    return ret;
  }

  if (numa_node_to_cpus(node_index, cpus) != 0) {
    ras_log(LOG_ERR, "Error reported by numa_node_to_cpus(node_index, cpus)");
    ret = NUMA_NODE_TO_CPUS_ERR;
    return ret;
  }

  if (numa_bitmask_weight(cpus) != 0) {
    ras_log(LOG_ERR, "Node index %d is not of a CPU-less node", node_index);
    ret = NOT_CPULESS_NODE_ERR;
    return ret;
  }

  return ret;
}

// Verify that the user-provided node is a valid CXL node
int verify_cpuless_node(const int &node_index) {
  int ret = 0;
  int max_node = numa_max_node();
  if (max_node < 0) {
    ras_log(LOG_CRIT, "Unable to get maximum value of NUMA node");
    ret = NUMA_MAX_NODE_ERR;
    return ret;
  }

  if ((node_index > max_node) || (node_index < 0)) {
    ras_log(LOG_WARNING, "Node index %d is outside the valid range [0-%d]",
            node_index, max_node);
    ret = INVALID_NUMA_INDEX_ERR;
    return ret;
  }

  ret = verify_zero_cpu_node(node_index);

  return ret;
}

// Verify CXL NUMA node for provided hardware address using regex
int verify_cxl_numa_node(const int &node_index, string &phy_addr_range) {
  int ret = 0;

  ret = verify_cpuless_node(node_index);
  if (ret != 0) {
    return ret;
  }

  // Creating the command-line using the provided node index
  string in = cf.grep_acpi_srat +
              string("|grep \"Node " + to_string(node_index) + string("\""));

  // Execute the command-line formed from above
  string out = cmd_exec(in);
  stringstream ss(out), ss2;
  string tok, tok2, ts, res;
  string regex_addr_range = cf.regex_addr_range;
  regex regex_acpi_srat(regex_addr_range);
  char *p = nullptr;
  long low, high, chk_low, chk_high;

  // Find the appropriate CXL device entry from /proc/iomem (if any) for the
  // NUMA node using the memory address range mentioned in /var/log/dmesg. The
  // memory address range mentioned in dmesg output for the concerned NUMA node
  // will be a subset of the range mentioned in /proc/iomem entry for the found
  // CXL device entry.
  while (getline(ss, tok, '\n')) {
    smatch m;
    if (regex_match(tok, m, regex_acpi_srat)) {
      res = m[1].str();
      remove_substr(res, "0x");
      p = nullptr;
      ts.assign(res);
      p = strtok((char *)ts.c_str(), "-");

      while (p != nullptr) {
        chk_low = strtoll(p, 0, 16);
        p = strtok(nullptr, "-");
        if (p != nullptr) {
          chk_high = strtoll(p, 0, 16);
        }
        p = strtok(nullptr, "-");
      }
      p = nullptr;
      string t = cf.grep_CXL;
      out = "";
      out = cmd_exec(t);
      ss2 << out;
      while (getline(ss2, tok2, '\n')) {
        p = strtok((char *)tok2.c_str(), ":");

        while (p != nullptr) {
          ts.assign(p);
          trim(ts);
          p = NULL;
          p = strtok((char *)ts.c_str(), "-");

          while (p != nullptr) {
            low = strtoll(p, 0, 16);
            p = strtok(nullptr, "-");
            if (p != nullptr) {
              high = strtoll(p, 0, 16);
            }
            p = strtok(nullptr, "-");
          }

          if (((chk_low >= low) && (chk_low <= high)) &&
              ((chk_high >= low) && (chk_high <= high))) {
            phy_addr_range = res;
            ret = 0;
            return ret;

          } else {
            ret = IOMEM_NOT_MATCHING_ACPI_SRAT_ERR;
          }
          p = strtok(nullptr, ":");
        }
      }
      if (ret != 0) {
        ras_log(LOG_CRIT,
                "Cannot find physical address in ACPI:SRAT entries of "
                "/var/log/dmesg with the CXL node in /proc/iomem output");
        return ret;
      }
    }
  }
  return ret;
}

// Verify hardware address in the range valid for the NUMA node
int verify_numa_node_addr(const int &node_index, const string &addr) {
  int ret = 0;
  string res;

  ret = verify_cxl_numa_node(node_index, res);
  if (ret == 0) {
    int pos = res.find("-");
    string low = res.substr(0, pos);
    string high = res.substr(pos + 1);

    long addr_low = strtoll(low.c_str(), NULL, 16);
    long addr_high = strtoll(high.c_str(), NULL, 16);
    long l_addr = strtoll(addr.c_str(), NULL, 16);

    if ((l_addr >= addr_low) && (l_addr <= addr_high))
      ret = 0;
    else {
      ras_log(LOG_WARNING,
              "Address provided %s is NOT valid for NUMA node %d. "
              "The valid range is [%s-%s]",
              addr.c_str(), node_index, low.c_str(), high.c_str());
      ret = ADDRESS_NOT_OF_NUMA_NODE_ERR;
    }
  }

  return ret;
}

int allocate_memory_on_numa_node(const int &noden) {
  /* Allocate on user-provided CXL node*/
  void *ptr;
  uintptr_t paddr;
  int ret = 0;
  ras_log(LOG_INFO, "Manually allocating memory on node %d", noden);

  if ((ptr = numa_alloc_onnode(NUMA_ALLOCATION_SIZE, noden)) == 0) {
    ras_log(LOG_CRIT, "Problem in %s line %d allocating memory", __FILE__,
            __LINE__);
    ret = NUMA_ALLOC_ON_NODE_ERR;
    return ret;
  }

  /***
   * Initialization memory allocated by libnuma required;
   * otherwise, node is not allocated
   */
  strcpy((char *)ptr, "*");

  // Virtual to physical mapping of the allocated address on the CXL node
  pid_t self_pid;

  self_pid = getpid();
  if (virt_to_phys_user(&paddr, self_pid, (uintptr_t)ptr)) {
    ras_log(LOG_ERR,
            "Failure in mapping virtual to physical addresss of \
                a NUMA CXL node");
    ret = FAILURE_TO_MAP_VIRTUAL_TO_PHYSICAL_MEM_ERR;
    return ret;
  };
  ras_log(LOG_NOTICE,
          "Physical address of memory alloc on NUMA CXL node: 0x%jx",
          (uintmax_t)paddr);

  // Freeing memory allocated using NUMA library
  numa_free((void *)ptr, NUMA_ALLOCATION_SIZE);
  ras_log(LOG_NOTICE, "NUMA allocated memory after numa_free is on node %d",
          get_node(ptr));

  return 0;
}

// Get file size of config.json
long get_file_size(std::string filename) {
  struct stat stat_buf;
  int rc = stat(filename.c_str(), &stat_buf);
  return rc == 0 ? stat_buf.st_size : -1;
}

// Determine the VFS block size
int block_size() {
  struct statvfs vfs_stat;
  if (statvfs("/", &vfs_stat) == 0) {
    return vfs_stat.f_bsize;
  } else {
    return 4096;
  }
}

/***
 * Initialization to to start a log file and read magic strings from
 * config.json file
 */
int init() {
  int ret = 0;
  FILE *file;  // descriptor for log file
  setlogmask(LOG_UPTO(LOG_INFO));
  openlog(APP_LOG, LOG_PERROR | LOG_CONS | LOG_PID | LOG_NDELAY, LOG_LOCAL1);

  ras_log(LOG_NOTICE, "Program started by User %d", getuid());

  // Open the file for reading
  file = fopen(CONFIG_FILE, "r");
  if (file == nullptr) {
    ras_log(LOG_ERR, "Failed to open configuration file %s", CONFIG_FILE);
    ret = CONFIG_FILE_NOT_AVAILABLE_ERR;
    return ret;
  }

  long sz = get_file_size(CONFIG_FILE);
  if (sz == -1) {
    ras_log(LOG_ERR, "Invalid size of configuration file %s", CONFIG_FILE);
    ret = INVALID_CONFIG_FILE_SIZE_ERR;
    return ret;
  }

  char readBuffer[sz + 1];
  FileReadStream is(file, readBuffer, block_size());

  // Parse the JSON data using a Document object
  Document data;
  data.ParseStream(is);

  if (data.HasParseError()) {
    ras_log(LOG_ERR, "Config file %s parsing error: %d. Error (offset %ld): %s",
            CONFIG_FILE, data.GetParseError(), data.GetErrorOffset(),
            GetParseError_En(data.GetParseError()));
    ret = CONFIG_FILE_PARSE_ERR;
    return ret;
  }
  // Close the config file
  fclose(file);

  if (data.HasMember("grep_CXL") && data["grep_CXL"].IsString()) {
    cf.grep_CXL = data["grep_CXL"].GetString();
    ras_log(LOG_INFO, "grep_CXL: %s", cf.grep_CXL.c_str());
  } else {
    ras_log(LOG_ERR, "The required key 'grep_CXL' not found in config file %s",
            CONFIG_FILE);
    ret = GREP_CXL_MISSING_ERR;
    return ret;
  }

  if (data.HasMember("grep_acpi_srat") && data["grep_acpi_srat"].IsString()) {
    cf.grep_acpi_srat = data["grep_acpi_srat"].GetString();
    ras_log(LOG_INFO, "grep_acpi_srat: %s", cf.grep_acpi_srat.c_str());
  } else {
    ras_log(LOG_ERR,
            "The required key 'grep_acpi_srat' not found in config file %s",
            CONFIG_FILE);
    ret = GREP_ACPI_SRAT_MISSING_ERR;
    return ret;
  }

  if (data.HasMember("regex_iomem") && data["regex_iomem"].IsString()) {
    cf.regex_iomem = data["regex_iomem"].GetString();
    ras_log(LOG_INFO, "reg_iomem: %s", cf.regex_iomem.c_str());
  } else {
    ras_log(LOG_ERR,
            "The required key 'regex_iomem' not found in config file %s",
            CONFIG_FILE);
    ret = REGEX_IOMEM_MISSING_ERR;
    return ret;
  }

  if (data.HasMember("regex_addr_range") &&
      data["regex_addr_range"].IsString()) {
    cf.regex_addr_range = data["regex_addr_range"].GetString();
    ras_log(LOG_INFO, "regex_addr_range: %s", cf.regex_addr_range.c_str());
  } else {
    ras_log(LOG_ERR,
            "The required key 'regex_addr_range' not found in config file %s",
            CONFIG_FILE);
    ret = REGEX_ADDR_RANGE_MISSING_ERR;
    return ret;
  }

  return ret;
}

void usage() {
  char buf[] =
      "USAGE: svk_ras_einj -n <CXL_node_index> [-l <Value of physical memory "
      "address "
      "for the provied CXL node index in hexadecimal "
      "format {e.g. '0xabcd1234'}>](optional)";
  ras_log(LOG_ERR, "%s", buf);
  cout << buf << endl;
}

int main(int argc, char *argv[]) {
  int ret = 0;
  if (argc < 3) {
    usage();
    ret = USAGE_ERR;
    return ret;
  }

  stringstream s;

  if ((ret = init()) != 0) {
    ras_log(LOG_ERR, "Initialization failed! Return Value: %d", ret);
    ret = INIT_ERR;
    return ret;
  }

  int noden, c;
  size_t len;
  string paddr = "", ts;

  while ((c = getopt(argc, argv, "n:l:h")) != -1) switch (c) {
      case 'n':
        for (size_t i = 0; i < strlen(optarg); ++i) {
          if (!isdigit(optarg[i])) {
            ras_log(LOG_ERR, "NUMA node index %s is an invalid entry", optarg);
            ret = OPT_ERR;
            return ret;
	  }
        }
        noden = strtol(optarg, NULL, 0);
        break;
      case 'l':
        len = strlen(optarg);
        if (len <= 2 || strncmp(optarg, "0x", 2) != 0) {
          ras_log(LOG_ERR, "Invalid entry for physical memory address: %s",
                  optarg);
          ret = OPT_ERR;
          return ret;
        }
        for (size_t i = 2; i < len; ++i) {
          if (!isxdigit(optarg[i])) {
            ras_log(LOG_ERR, "Invalid entry for physical memory address: %s",
                    optarg);
            ret = OPT_ERR;
            return ret;
          }
        }
        paddr = optarg;
        break;
      default:
        usage();
        ret = OPT_ERR;
        return ret;
    }

  if (numa_available() < 0) {
    ras_log(LOG_WARNING, "NUMA feature not available");
    ret = NUMA_NOT_AVAILABLE_ERR;
    return ret;
  }

  string addr_range;

  ret = verify_cxl_numa_node(noden, addr_range);
  if (ret != 0) {
    ras_log(LOG_NOTICE, "The provided index %d is NOT of a CXL node", noden);
    return ret;
  } else {
    ras_log(LOG_NOTICE, "The provided index %d is of a CXL node", noden);
  }

  // Verify provided physical address
  if (paddr.length() > 0) {
    if (verify_numa_node_addr(noden, paddr) == 0) {
      ras_log(LOG_NOTICE, "The address %s [within %s] is valid on node %d",
              paddr.c_str(), addr_range.c_str(), noden);
    } else {
      ras_log(LOG_NOTICE, "The address %s [outside %s] is invalid on node %d",
              paddr.c_str(), addr_range.c_str(), noden);
    }
  } else if (paddr.length() == 0) {
    ret = allocate_memory_on_numa_node(noden);
    if (ret != 0) {
      ras_log(LOG_CRIT, "Failed to allocate memory on NUMA node %d", noden);
      return ret;
    }
  }

  return 0;
}
