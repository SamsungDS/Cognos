#include <execinfo.h>
#include <fcntl.h>
#include <getopt.h>
#include <numa.h>
#include <numaif.h>
#include <rapidjson/document.h>
#include <rapidjson/error/en.h>
#include <rapidjson/error/error.h>
#include <rapidjson/filereadstream.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <syslog.h>
#include <ucontext.h>
#include <unistd.h>

#include <array>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <memory>
#include <regex>
#include <sstream>
#include <stack>
#include <stdexcept>
#include <string>
#include <thread>

#define NUMA_ALLOCATION_SIZE 4096UL
#define CONFIG_FILE "config.json"
#define APP_LOG "svk_ras_einj.log"
#define ras_log(x, ...) syslog(x, ##__VA_ARGS__)
#define MAP_SIZE 4096UL
#define MAP_MASK (MAP_SIZE - 1)
#define fname "/tmp/svk_ras_inject"
#define STACK_LENGTH 50
#define CPU "{cpu}"
#define ADDR "{addr}"
#define MCE_INJECT_SAMPLE_FILE "/tmp/test_corrected"
#define MAX_BUF 1024

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
  IOMEM_NOT_MATCHING_ACPI_SRAT_ERR,
  UNABLE_OPEN_DEV_MEM,
  MMAP_FAIL,
  INVALID_PID,
  SIGACTION_FAIL,
  PRCTL_FAIL,
  MADVISE_FAIL,
  MKFIFO_FAIL,
  MCE_INJECT_TEMPLARE_STRING_MISSING_ERR,
  RASDAEMON_EXEC_COMMAND_MISSING_ERR
};

/* This structure mirrors the one found in /usr/include/asm/ucontext.h */
typedef struct _sig_ucontext {
  unsigned long uc_flags;
  ucontext_t *uc_link;
  stack_t uc_stack;
  sigcontext uc_mcontext;
  sigset_t uc_sigmask;
} sig_ucontext_t;

// Wrapper around syslog
// void ras_log(int pri, char *buf) { syslog(pri, "%s", buf); }

// Signal handler for SIGBUS, etc. for memory access on poisoned page
void signal_handler(int sig_num, siginfo_t *info, void *ucontext) {
  void *caller_address;
  sig_ucontext_t *uc;
  void *array[STACK_LENGTH];
  char **messages;
  int size, i;

  uc = (sig_ucontext_t *)ucontext;
/* Get the address at the time the signal was raised */
#if defined(__i386__)                            // gcc specific
  caller_address = (void *)uc->uc_mcontext.eip;  // EIP: x86 specific
#elif defined(__x86_64__)                        // gcc specific
  caller_address = (void *)uc->uc_mcontext.rip;  // RIP: x86_64 specific
#else
#error Unsupported architecture. // Add support for other arch.
#endif

  ras_log(LOG_ERR, "signal %d (%s), address is %p from %p\n", sig_num,
          strsignal(sig_num), info->si_addr, (void *)caller_address);

  size = backtrace(array, STACK_LENGTH);

  /* overwrite sigaction with caller's address */
  array[1] = caller_address;

  messages = backtrace_symbols(array, size);

  /* skip first stack frame (points here) */
  for (i = 1; i < size && messages != NULL; ++i) {
    fprintf(stderr, "[bt]: (%d) %s\n", i, messages[i]);
  }

  free(messages);

  exit(sig_num);
}

// Creating a sample file that can be used with mce-inject
void file_write(const char *filepath, const char *data) {
  FILE *fp = fopen(filepath, "w");
  if (fp != NULL) {
    fputs(data, fp);
    fclose(fp);
  }
}

// Converting a template string replacing parameters with custon values
// Converting a tempalte string to mce-inject error injection sample string
void apply_tmpl(string &tmpl, const string &rep, const string &val) {
  tmpl.replace(tmpl.find(rep), rep.length(), val);
}

// Parse the pagemap entry for the given virtual address.
int pagemap_get_entry(PagemapEntry *entry, int pagemap_fd, uintptr_t vaddr) {
  if (vaddr == 0) return 1;

  size_t nread;
  ssize_t ret;
  uint64_t data;
  uintptr_t vpn;

  /**********************************************************************
   * sizeof(sysconf(_SC_PAGE_SIZE)) -> 4096 bytes
   * sizeof(PagemapEntry) -> 8 bytes
   * sizeof(uint64_t) -> 8 bytes
   * and that stuct PagemapEntry has specific bit-field sized members designed
   * as per kernel's specification mentioned in the URL
   * https://www.kernel.org/doc/Documentation/vm/pagemap.txt
   * Now, as per man page of pread:
   * ssize_t pread(int fd, void *buf, size_t count, off_t offset);
   * pread() reads up to count bytes from file descriptor fd at offset (from
   * the start of the file) into the buffer starting at buf. The file offset
   * is not changed. The variable vpn "vpn" is the original starting offset
   * aligned on the page size (i.e. sysconf(_SC_PAGE_SIZE) for that particular
   * virtual address (vaddr in this case) in the file containing info about
   * page mapping for a paricular process. Now each 8 bytes
   * (i.e. 64 bits = sizeof(uint64_t)) in that pagemap file has info about
   * one page size i.e. 4096 bytes of virtual address space.

   * Moreover, sizeof() library call is with the variable of type uint64_t i.e
   * if the number of bytes read is less than size of uint64_t (and this is
   * per kernel documentation requirement mentioned above) then the
   * statements inside `while (nread < sizeof(data)) ` will be executed till
   * the total amount read using pread is equal to or less than
   * sizeof(uint64_t) and the pread returns 0 on EOF or negative on pread
   * failure.
   ********************************************************************/

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
    ras_log(LOG_DEBUG, "Node index %d is not of a CPU-less node", node_index);
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
    ras_log(LOG_NOTICE, "Node index %d is outside the valid range [0-%d]",
            node_index, max_node);
    ret = INVALID_NUMA_INDEX_ERR;
    return ret;
  }

  ret = verify_zero_cpu_node(node_index);
  if (ret == 0) {
    ras_log(LOG_DEBUG, "Node index %d is of a CPU-less NUMA node", node_index);
  }

  return ret;
}

// Show details about all NUMA nodes
int show_details_of_numa_nodes() {
  int ret = 0;
  string in;
  size_t max_node = numa_max_node();
  if (max_node < 0) {
    ras_log(LOG_CRIT, "Unable to get maximum value of NUMA node");
    ret = NUMA_MAX_NODE_ERR;
    return ret;
  }

  for (size_t i = 0; i <= max_node; ++i) {
    // Creating the command-line using the provided node index
    in = cf.grep_acpi_srat +
         string("|grep \"Node " + to_string(i) + string("\""));

    // Execute the command-line formed from above
    string out = cmd_exec(in);
    stringstream ss(out), ss2;
    string tok, res;
    string regex_addr_range = cf.regex_addr_range;
    regex regex_acpi_srat(regex_addr_range);

    while (getline(ss, tok, '\n')) {
      smatch m;
      if (regex_match(tok, m, regex_acpi_srat)) {
        res = m[1].str();
        remove_substr(res, "0x");
        ras_log(LOG_INFO, "Node: %-5ldCXL: %-7s Physical Address Range: %-40s",
                i,
                ((verify_cpuless_node(i) == NOT_CPULESS_NODE_ERR) ? "False"
                                                                  : "True"),
                res.c_str());
      }
    }
  }
  return ret;
}

// Verify CXL NUMA node for provided hardware address using regex
int verify_cxl_numa_node(const int &node_index) {
  int ret = 0;

  ret = verify_cpuless_node(node_index);
  return ret;
}

int get_numa_node_address_range(const int &node_index, const bool cxl_node,
                                string &phy_addr_range) {
  int ret = 0;
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
  stack<string> st;

  // Find the appropriate CXL device entry from /proc/iomem (if any) for the
  // NUMA node using the memory address range mentioned in /var/log/dmesg. The
  // memory address range mentioned in dmesg output for the concerned NUMA node
  // will be a subset of the range mentioned in /proc/iomem entry for the found
  // CXL device entry.
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
      if (cxl_node == false) continue;

      // Continue if the node index is of a CXL node
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
            ret = 0;
            return ret;

          } else {
            ret = IOMEM_NOT_MATCHING_ACPI_SRAT_ERR;
          }
          p = strtok(nullptr, ":");
        }
      }
    }
    if (ret != 0) {
      ras_log(LOG_DEBUG,
              "Cannot find physical address in ACPI:SRAT entries of "
              "/var/log/dmesg with the CXL node in /proc/iomem output");
      return ret;
    }
  }
  return ret;
}

// Verify hardware address in the range valid for the NUMA node
int verify_numa_node_addr(const int &node_index, const bool cxl_node,
                          const string &addr, string &addr_range) {
  int ret = 0;
  string res;

  ret = get_numa_node_address_range(node_index, cxl_node, res);

  // Get the address range from `cat /proc/iomem` output for a valid
  // NUMA node (i.e. a CXL or a non-CXL NUMA node)
  if ((ret == 0) || (ret == IOMEM_NOT_MATCHING_ACPI_SRAT_ERR)) {
    trim(res);
    addr_range = res;
    string low, high, tok;
    long addr_low, addr_high, l_addr;
    stringstream ss(res);

    // Verify if the address provided is valid in the range specified in
    // the `cat /proc/iomem` output or from the /var/log/dmesg output
    while (getline(ss, tok, '-')) {
      if (low.empty()) {
        low = tok;
        addr_low = strtoll(low.c_str(), NULL, 16);
      } else if (high.empty()) {
        high = tok;
        addr_high = strtoll(high.c_str(), NULL, 16);
      }
      l_addr = strtoll(addr.c_str(), NULL, 16);

      if ((l_addr >= addr_low) && (l_addr <= addr_high)) {
        ras_log(LOG_NOTICE, "Address provided %s is valid for node %d",
                addr.c_str(), node_index);
        ret = 0;
        return ret;
      }
    }

    ras_log(LOG_DEBUG,
            "Physical address provided %s is NOT valid for NUMA node %d\n"
            "The valid physical address range is [%s-%s]",
            addr.c_str(), node_index, low.c_str(), high.c_str());
    ret = ADDRESS_NOT_OF_NUMA_NODE_ERR;
  }

  return ret;
}

int allocate_memory_on_numa_node(const int &noden, string &addr) {
  /* Allocate on user-provided node*/
  void *ptr;
  uintptr_t paddr;
  int ret = 0;
  ras_log(LOG_DEBUG, "Manually allocating memory on node %d", noden);

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

  // Virtual to physical mapping of the allocated address on the NUMA node
  pid_t self_pid;

  self_pid = getpid();
  if (virt_to_phys_user(&paddr, self_pid, (uintptr_t)ptr)) {
    ras_log(LOG_ERR,
            "Failure in mapping virtual to physical addresss of a NUMA"
            " CXL node");
    ret = FAILURE_TO_MAP_VIRTUAL_TO_PHYSICAL_MEM_ERR;
    return ret;
  };
  ras_log(LOG_NOTICE,
          "Physical address of memory alloc on NUMA node %d: 0x%jx. "
          "This address can be used to inject error using \'-e\' option",
          noden, (uintmax_t)paddr);

  char t[20];
  sprintf(t, "%lx", paddr);
  addr.assign(t);

  // Freeing memory allocated using NUMA library
  numa_free((void *)ptr, NUMA_ALLOCATION_SIZE);
  ras_log(LOG_DEBUG, "NUMA allocated memory after numa_free is on node %d",
          get_node(ptr));

  return 0;
}

// Error injection using madvise with MADV_HWPOISON flag
int error_injection(void *paddr) {
  int ret = 0;

  // Using prctl to set the policy for signal trigger only after memory access
  // of the poisoned address
  if (prctl(PR_MCE_KILL, PR_MCE_KILL_SET, PR_MCE_KILL_LATE, 0L, 0L) != 0) {
    ras_log(LOG_CRIT, "prctl error");
    ret = PRCTL_FAIL;
    return ret;
  }

  // Inject memory failure using madvise with MADV_HWPOISON
  int result = madvise(paddr, sysconf(_SC_PAGE_SIZE), MADV_HWPOISON);
  if (result == -1) {
    ras_log(LOG_CRIT, "madvise failed");
    ret = MADVISE_FAIL;
    return ret;
  }

  // Attempt to access the poisoned memory (will likely trigger a SIGBUS)
  unsigned int *value = (unsigned int *)paddr;
  ras_log(LOG_INFO, "Value at poisoned memory: %d\n", *value);

  return ret;
}

// Mmap a physical address using /dev/mem to get a virtual address that will
// be used for error injection using madvise
int error_inject_using_paddr(string lpaddr) {
  int ret = 0, fd;
  void *map_base_d;
  uintptr_t virt_addr;
  off_t target;
  target = strtoul(lpaddr.c_str(), NULL, 0);

  if ((fd = open("/dev/mem", O_RDWR | O_SYNC)) == -1) {
    ras_log(LOG_CRIT, "Unable to open /dev/mem");
    ret = UNABLE_OPEN_DEV_MEM;
    return ret;
  }

  // mmap using the inode descriptor of /dev/mem and offset of physical address
  map_base_d = (void *)mmap(0, MAP_SIZE, PROT_READ | PROT_WRITE,
                            MAP_ANONYMOUS | MAP_SHARED, fd, target & ~MAP_MASK);
  // MAP_ANONYMOUS | MAP_PRIVATE, fd, target & ~MAP_MASK);
  if (map_base_d == MAP_FAILED) {
    ras_log(LOG_CRIT, "Unable to mmap using physical address %ld", target);
    close(fd);
    ret = MMAP_FAIL;
    return ret;
  }

  ras_log(LOG_NOTICE, "Memory mapped at address %p.\n", map_base_d);

  virt_addr = (uintptr_t)map_base_d + (target & MAP_MASK);
  unsigned int *p = reinterpret_cast<unsigned int *>(virt_addr);
  *p = 0x1234;
  ras_log(LOG_INFO, "Value at address 0x%lX: 0x%X\n", virt_addr,
          *(unsigned int *)(virt_addr));

  // Error injection using mmap address using the physical address offset and
  // /dev/mem
  ret = error_injection(map_base_d);
  if (ret != 0) {
    ras_log(LOG_ERR, "Error while injecting error using physical address 0x%lX",
            virt_addr);
    close(fd);
    munmap(map_base_d, MAP_SIZE);
    return ret;
  }

  close(fd);
  munmap(map_base_d, MAP_SIZE);

  return ret;
}

// Readind the file written to by rasdaemon
int fifo_read(char *fifo_name, string &dstr) {
  char buf[MAX_BUF];
  int fd = -1, bytesread, ret = 0;

  /* open, read, and display the message from the FIFO */
  fd = open(fifo_name, O_RDONLY);
  if (fd == -1) {
    // Create the named FIFO
    fd = mkfifo(fifo_name, 0666);
    if (fd == -1) {
      ras_log(LOG_ERR, "Error with mkfifo");
      return MKFIFO_FAIL;
    }
    ras_log(LOG_INFO, "Created fifo %s", fifo_name);
  }
  // Show rasdaemon output
  while (1) {
    bytesread = read(fd, buf, MAX_BUF - 1);
    if (bytesread > 0) {
      buf[bytesread] = '\0';
      ras_log(LOG_NOTICE, "Received: %s\n", buf);
    } else
      break;
  }
  close(fd);
  unlink(fifo_name);
  return ret;
}

// Start rasdaemon and dump its output to a file.  Those outputs are
// captured by reading the file and logging it
int prepare_mce_inject_error_capture_using_rasdaemon() {
  int ret = 0;
  char *fifo_name = (char *)(fname);

  // Create a sample test_corrected error injection file for mce-inject
  string str = cf.mce_inject_template_string;
  int cpu = sched_getcpu();
  int node = numa_node_of_cpu(cpu);

  apply_tmpl(str, CPU, to_string(cpu));
  string dstr;
  ret = allocate_memory_on_numa_node(node, dstr);
  if (ret != 0) {
    printf("Failed to allocate memory on NUMA node %d", node);
    return ret;
  }
  apply_tmpl(str, ADDR, string("0x") + dstr);
  file_write(MCE_INJECT_SAMPLE_FILE, str.c_str());

  // Start rasdaemon and redirect output to a file in one thread and that file
  // is read in a separate thread
  string scmd;
  scmd = (string)(cf.rasdaemon_exec_command) + string(fifo_name);
  thread tproc(cmd_exec, ref(scmd));
  thread tpipe(fifo_read, fifo_name, ref(dstr));

  tpipe.join();
  tproc.join();

  return ret;
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

  if (data.HasMember("mce_inject_template_string") &&
      data["mce_inject_template_string"].IsString()) {
    cf.mce_inject_template_string =
        data["mce_inject_template_string"].GetString();
    ras_log(LOG_INFO, "mce_inject_template_string: %s",
            cf.mce_inject_template_string.c_str());
  } else {
    ras_log(LOG_ERR,
            "The required key 'mce_inject_template_string' not found in config "
            "file %s",
            CONFIG_FILE);
    ret = MCE_INJECT_TEMPLARE_STRING_MISSING_ERR;
    return ret;
  }

  if (data.HasMember("rasdaemon_exec_command") &&
      data["rasdaemon_exec_command"].IsString()) {
    cf.rasdaemon_exec_command = data["rasdaemon_exec_command"].GetString();
    ras_log(LOG_INFO, "rasdaemon_exec_command: %s",
            cf.rasdaemon_exec_command.c_str());
  } else {
    ras_log(
        LOG_ERR,
        "The required key 'rasdaemon_exec_command' not found in config file %s",
        CONFIG_FILE);
    ret = RASDAEMON_EXEC_COMMAND_MISSING_ERR;
    return ret;
  }

  return ret;
}

void usage() {
  char buf[] =
      "USAGE: svk_ras_einj [-n <NUMA node index>] [-l <Value of physical memory"
      " address valid for the NUMA node index in hexadecimal format "
      "{example: '0xabcd1234'}>] [-e (for injecting error)](optional)\n"
      "OR \n"
      "svk_ras_einj [-p <external process ID>] [-v <virtual address of "
      "process ID>] [-e (for injecting error)](optional)\n"
      "OR \n"
      "svk_ras_einj [-n <CXL_node_index>] \n"
      "OR \n"
      "svk_ras_einj [-c (to capture errors using rasdaemon)]\n"
      "OR \n"
      "svk_ras_einj [-s (to show details of NUMA nodes)]\n"
      "OR \n"
      "svk_ras_einj -h (to show this usage text)\n";

  ras_log(LOG_ERR, "%s", buf);
  cout << buf << endl;
}

int main(int argc, char *argv[]) {
  int ret = 0;
  stringstream s;

  if ((ret = init()) != 0) {
    ras_log(LOG_ERR, "Initialization failed! Return Value: %d", ret);
    ret = INIT_ERR;
    return ret;
  }

  struct sigaction sigact;

  sigact.sa_sigaction = signal_handler;
  sigact.sa_flags = SA_RESTART | SA_SIGINFO;

  if (sigaction(SIGBUS, &sigact, (struct sigaction *)NULL) != 0) {
    ras_log(LOG_CRIT, "Error setting signal handler for %d (%s)\n", SIGBUS,
            strsignal(SIGBUS));
    ret = SIGACTION_FAIL;
    return ret;
  }

  int noden = -1, pid = -1, c;
  size_t len;
  string paddr = "", vaddr = "", ts;
  bool raise_error = false;

  while ((c = getopt(argc, argv, "n:l:v:p:cesh")) != -1) switch (c) {
      case 'n':
        for (size_t i = 0; i < strlen(optarg); ++i) {
          if (!isdigit(optarg[i])) {
            ras_log(LOG_ERR, "NUMA node index %s is an invalid entry", optarg);
            ret = OPT_ERR;
            return ret;
          }
        }
        noden = strtol(optarg, NULL, 0);
        if (noden < 0) {
          ras_log(LOG_ERR,
                  "NUMA node index %d is an invalid entry.\n"
                  "Please consult the NUMA node details below to get"
                  " a valid node index",
                  noden);
          ret = show_details_of_numa_nodes();
          if (ret != 0) {
            ras_log(LOG_ERR, "Error in getting detils of NUMA nodes");
            return ret;
          }
        }
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
      case 'v':
        len = strlen(optarg);
        if (len <= 2 || strncmp(optarg, "0x", 2) != 0) {
          ras_log(LOG_ERR, "Invalid entry for virtual memory address: %s",
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
        vaddr = optarg;
        break;
      case 'p':
        len = strlen(optarg);
        for (size_t i = 0; i < len; ++i) {
          if (!isdigit(optarg[i])) {
            ras_log(LOG_ERR, "Process ID provided %s is an invalid entry",
                    optarg);
            ret = OPT_ERR;
            return ret;
          }
        }
        pid = strtol(optarg, NULL, 0);
        break;
      case 'e':
        raise_error = true;
        break;
      case 's':
        ret = show_details_of_numa_nodes();
        if (ret != 0) {
          ras_log(LOG_ERR, "Error in getting details of NUMA nodes");
          return ret;
        }
        return ret;
        break;
      case 'c':
        ret = prepare_mce_inject_error_capture_using_rasdaemon();
        if (ret != 0) {
          ras_log(LOG_ERR, "Error in capturing rasdaemon error output");
          return ret;
        }
        return ret;
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

  bool cxl_node = false;

  // The command-line arguments are processed in the following order:
  // 0) Show usage is -h option is used
  // 1) Provide NUMA node details (node index, CXL NUMA node or not, physical
  // address range as allocated by the kernel) if -s option is used
  // 2) If node index and PID of external process not provided, print usage and
  // return
  // 3) If node index and physical address provided, validate physical address
  // with NUMA node index and use that physical address using /dev/mem to mmap
  // to get a virtual address in this process address space ti inject error
  // using madvise using MADV_HWPOISON flag
  // 4) If PID of external process and virtual address in that process address
  // provided, use that to get corresponding physical address and mmap that
  // physical address in this process using /dev/mem and use that to inject
  // error using madvise MADV_HWPOISON flag
  // 5) If only a node index is provided, validate that as a valid node index
  // and provide a sample physical address on that node as allocated by the
  // kernel
  // 6) Start rasdaemon and mce-inject caturing threads if '-c' option is 
  // provided 

  if ((noden == -1) && (pid == -1)) {
    usage();
    return ret;
  } else if ((noden >= 0) && (paddr.length() > 0)) {
    ret = verify_cxl_numa_node(noden);
    if (ret != 0) {
      cxl_node = false;
      if (ret == NOT_CPULESS_NODE_ERR)
        ras_log(LOG_NOTICE, "The provided index %d is NOT of a CXL node",
                noden);
      else {
        ras_log(LOG_NOTICE, "Verification of CXL node %d failed", noden);
        return ret;
      }

    } else {
      cxl_node = true;
      ras_log(LOG_NOTICE, "The provided index %d is of a CXL node", noden);
    }

    // Verify provided physical address
    string addr_range;
    ret = verify_numa_node_addr(noden, cxl_node, paddr, addr_range);
    if (ret == 0) {
      ras_log(LOG_NOTICE,
              "The address %s [within range %s] is valid on NUMA node %d",
              paddr.c_str(), addr_range.c_str(), noden);
    } else {
      ras_log(LOG_NOTICE,
              "The address %s [outside range %s] NOT valid on NUMA node %d. ",
              paddr.c_str(), addr_range.c_str(), noden);
    }
    if (raise_error == true) {
      remove_substr(paddr, "0x");
      ret = error_inject_using_paddr(paddr);
      if (ret != 0) {
        ras_log(
            LOG_ERR,
            "Error during steps to error injection using physical address %s",
            paddr.c_str());
        return ret;
      }

    } else {
      ras_log(LOG_NOTICE,
              "Please add \'-e\' to inject error using valid physical address");
      return ret;
    }
  }

  else if ((pid >= 1) && (vaddr.length() > 0)) {
    int ret = 0;
    if (pid < 0) {
      ras_log(LOG_ERR, "Invalid pid %d", pid);
      ret = INVALID_PID;
      return ret;
    }
    uintptr_t lvaddr, lpaddr;
    string s_paddr;

    lvaddr = strtoll(vaddr.c_str(), NULL, 16);

    ret = virt_to_phys_user(&lpaddr, pid, lvaddr);
    if (ret != 0) {
      ras_log(LOG_ERR,
              "Failed to get physical address using pid %d and virtual address "
              "0x%lX",
              pid, lvaddr);
      return ret;
    }

    ras_log(LOG_NOTICE,
            "The physical address:0x%lX can/will be used for error injection",
            lpaddr);

    if (raise_error == true) {
      sprintf(s_paddr.data(), "%lX", lpaddr);
      ret = error_inject_using_paddr(s_paddr);
      if (ret != 0) {
        ras_log(LOG_ERR,
                "Error while injecting error using physical address 0x%lX",
                lpaddr);
        return ret;
      }
    } else {
      ras_log(LOG_NOTICE,
              "Please add \'-e\' to inject error using valid PID and virtual "
              "address");
      return ret;
    }
  } else if ((pid >= 1) && (vaddr.length() == 0)) {
    usage();
    return ret;
  } else if (noden >= 0) {
    ret = verify_cxl_numa_node(noden);
    if (ret != 0) {
      cxl_node = false;
      if (ret == NOT_CPULESS_NODE_ERR)
        ras_log(LOG_NOTICE, "The provided index %d is NOT of a CXL node",
                noden);
      else {
        ras_log(LOG_DEBUG, "Verification of CXL node %d failed", noden);
        return ret;
      }

    } else {
      cxl_node = true;
      ras_log(LOG_NOTICE, "The provided index %d is of a CXL node", noden);
    }

    string dstr;
    ret = allocate_memory_on_numa_node(noden, dstr);
    if (ret != 0) {
      ras_log(LOG_CRIT, "Failed to allocate memory on NUMA node %d", noden);
      return ret;
    }
  }

  return 0;
}
