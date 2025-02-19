/*  Memory Solutions Lab RAS Utility
 *
 */
 
#include <fcntl.h>
#include <getopt.h>
#include <numa.h>
#include <numaif.h>
#include <stdio.h>
#include <stdlib.h>
#include <syslog.h>
#include <unistd.h>

#include <array>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <memory>
#include <nlohmann/json.hpp>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>

#define NUMA_ALLOCATION_SIZE 1024

using namespace std;
using json = nlohmann::json;

// Configuration global variables as defined in config.json
struct Config {
  string grep_CXL;
  string grep_acpi_srat;
  string regex_iomem;
  string regex_addr_range;
};

// Instantiation of global vars to be used as key-value pairs
Config cf;
FILE *fp;  // descriptor for log file

// Struct derived from https://www.kernel.org/doc/Documentation/vm/pagemap.txt
typedef struct {
  uint64_t pfn : 55;
  unsigned int soft_dirty : 1;
  unsigned int file_page : 1;
  unsigned int swapped : 1;
  unsigned int present : 1;
} PagemapEntry;

// Parse the pagemap entry for the given virtual address.
int pagemap_get_entry(PagemapEntry *entry, int pagemap_fd, uintptr_t vaddr) {
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
    return 1;
  }
  PagemapEntry entry;
  if (pagemap_get_entry(&entry, pagemap_fd, vaddr)) {
    return 1;
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
    syslog(LOG_CRIT, "Problem in %s line %d calling move_pages()", __FILE__,
           __LINE__);
    abort();
  }

  return (status[0]);
}

// Execute a command using popen/pclose
std::string exec(string &cmd) {
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
bool verify_zero_cpu_node(const int &node_index) {
  struct bitmask *cpus;

  // Assigning bits for CPUs and evaluating
  cpus = numa_allocate_cpumask();
  numa_node_to_cpus(node_index, cpus);
  if (numa_bitmask_weight(cpus) == 0) return true;

  return false;
}

// Verify CXL NUMA node for provided hardware address using regex
bool verify_cxl_numa_node(const int &node_index, string &phy_addr_range) {
  bool ret = false;

  // Creating the command-line using the provided node index
  string in = cf.grep_acpi_srat +
              string("|grep \"Node " + to_string(node_index) + string("\""));

  // Execute the command-line formed from above
  string out = exec(in);
  stringstream ss(out);
  string tok;
  string regex_addr_range = cf.regex_addr_range;
  regex regex_acpi_srat(regex_addr_range);

  while (getline(ss, tok, '\n')) {
    smatch m;
    if (regex_match(tok, m, regex_acpi_srat)) {
      string res = string(m[1]);
      remove_substr(res, "0x");
      string t = cf.grep_CXL + string("|grep ") + res;
      out = "";
      out = exec(t);
      if (out.substr(out.find(res), res.length()).compare(res) == 0) {
        ret = true;
        phy_addr_range = res;
      }
    }
  }
  return ret;
}

// Verify hardware address in the range valid for the NUMA node
bool verify_numa_node_addr(const int &node_index, const string &addr) {
  bool ret = false;
  string res;
  if (verify_cxl_numa_node(node_index, res) == true) {
    int pos = res.find("-");
    string low = res.substr(0, pos);
    string high = res.substr(pos + 1);

    long addr_low = strtoll(low.c_str(), NULL, 16);
    long addr_high = strtoll(high.c_str(), NULL, 16);
    long l_addr = strtol(addr.c_str(), NULL, 16);

    if ((l_addr >= addr_low) && (l_addr <= addr_high))
      ret = true;
    else
      ret = false;
  }
  return ret;
}

// Verify that the user-provided node is a valid CXL node
bool verify_cpuless_node(const int &node_index) {
  int max_node = numa_max_node();
  int ret = false;
  stringstream s;
  char buf[128];

  if ((node_index > max_node) || (node_index < 0)) {
    sprintf(buf, "Node index is outside valid range");
    syslog(LOG_WARNING, "%s", buf);
    return ret;
  }

  ret = verify_zero_cpu_node(node_index);

  return ret;
}

int allocate_memory_on_numa_node(const int &noden) {
  /* Allocate on user-provided CXL node*/
  void *ptr;
  uintptr_t paddr;
  char buf[256];
  sprintf(buf, "Manually allocating memory on node %d", noden);
  syslog(LOG_INFO, "%s", buf);

  if ((ptr = numa_alloc_onnode(NUMA_ALLOCATION_SIZE, noden)) == 0) {
    sprintf(buf, "Problem in %s line %d allocating memory", __FILE__, __LINE__);
    syslog(LOG_CRIT, "%s", buf);
    return (102);
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
    sprintf(buf,
            "Failure in mapping virtual to physical addresss of \
                a NUMA CXL node");
    syslog(LOG_ERR, "%s", buf);
    return (103);
  };
  sprintf(buf, "Physical address of memory alloc on NUMA CXL node: 0x%jx",
          (uintmax_t)paddr);
  syslog(LOG_NOTICE, "%s", buf);

  // Freeing memory allocated using NUMA library
  numa_free((void *)ptr, NUMA_ALLOCATION_SIZE);
  sprintf(buf, "NUMA allocated memory after numa_free is on node %d",
          get_node(ptr));
  syslog(LOG_NOTICE, "%s", buf);

  return 0;
}

/***
 * Initialization to to start a log file and read magic strings from from
 * config.json file
 */
int init() {
  setlogmask(LOG_UPTO(LOG_INFO));
  openlog("mslras.log", LOG_PERROR | LOG_CONS | LOG_PID | LOG_NDELAY,
          LOG_LOCAL1);

  syslog(LOG_NOTICE, "Program started by User %d", getuid());

  ifstream file("config.json");
  if (!file.is_open()) {
    syslog(LOG_ERR, "%s", "Failed to open configuration file config.json");
    return 2;
  }

  json data;
  try {
    data = json::parse(file);
  } catch (const json::parse_error &e) {
    syslog(LOG_WARNING, "JSON parse error: %s", e.what());
    return 3;
  }

  if (data.contains("grep_CXL")) {
    cf.grep_CXL = data["grep_CXL"];
    syslog(LOG_INFO, "grep_CXL: %s", cf.grep_CXL.c_str());
  }

  if (data.contains("grep_acpi_srat")) {
    cf.grep_acpi_srat = data["grep_acpi_srat"];
    syslog(LOG_INFO, "grep_acpi_srat: %s", cf.grep_acpi_srat.c_str());
  }

  if (data.contains("regex_iomem")) {
    cf.regex_iomem = data["regex_iomem"];
    syslog(LOG_INFO, "reg_iomem: %s", cf.regex_iomem.c_str());
  }

  if (data.contains("regex_addr_range")) {
    cf.regex_addr_range = data["regex_addr_range"];
    syslog(LOG_INFO, "regex_addr_range: %s", cf.regex_addr_range.c_str());
  }

  return 0;
}

void usage() {
  char buf[] =
      "USAGE: ras -n <CXL_node_index> [-l <physical address for \
		  testing on CXL node>(optional)]";
  syslog(LOG_WARNING, "%s", buf);
}

int main(int argc, char *argv[]) {
  if (argc < 3) {
    cout << "USAGE: ras -n <CXL_node_index> [-l <physical address for \
		testing on CXL node>(optional)]"
         << endl;
    return 1;
  }

  stringstream s;
  int ret = 0;
  char buf[128];

  if (init() != 0) {
    sprintf(buf, "Initialization failed!");
    syslog(LOG_ERR, "%s", buf);
    ret = 1;
    return ret;
  }

  int noden, c;
  string paddr = "";

  while ((c = getopt(argc, argv, "n:l:h")) != -1) switch (c) {
      case 'n':
        noden = strtol(optarg, NULL, 0);
        break;
      case 'l':
        paddr = optarg;
        break;
      default:
        usage();
        ret = 2;
        return ret;
    }

  if (numa_available() < 0) {
    syslog(LOG_WARNING, "%s", "NUMA featute not available");
    ret = 3;
    return ret;
  }

  string addr_range;
  s.str("");
  s.clear();
  if ((verify_cpuless_node(noden) == false) ||
      (verify_cxl_numa_node(noden, addr_range) == false)) {
    sprintf(buf, "The provided index %d is NOT of a CXL node", noden);
    syslog(LOG_NOTICE, "%s", buf);
    ret = 101;
    return ret;
  } else {
    sprintf(buf, "The provided index %d is of a CXL node", noden);
    syslog(LOG_NOTICE, "%s", buf);
  }

  // Verify provided physical address
  s.str("");
  s.clear();
  if (paddr.length() > 0) {
    if (verify_numa_node_addr(noden, paddr) == true) {
      sprintf(buf, "The address %s is valid on node %d", paddr.c_str(), noden);
      syslog(LOG_NOTICE, "%s", buf);
    } else {
      sprintf(buf, "The address %s is invalid on node %d", paddr.c_str(),
              noden);
      syslog(LOG_NOTICE, "%s", buf);
    }
  } else if (paddr.length() == 0) {
    allocate_memory_on_numa_node(noden);
  }

  return 0;
}
