#include "sc_cmmmp.h"  // implements all functions declared in sc_cmmmp.h

#include <jansson.h>

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#include <unordered_set>

#include "sc_api_structs.h"
#include "sc_utility.h"  // get_numa_memory_info, find_dev_type_map

namespace {

constexpr uint64_t kMiB = 1024ULL * 1024ULL;
constexpr char kCmmMpDeviceType[] = "CMM-MP";
constexpr char kCmmMpPoolDeviceType[] = "CMM-MP Pool";
constexpr char kCmmMpMpnDeviceType[] = "CMM-MP MPN";
constexpr char kBackendConnection[] = "Ethernet (pool back-end)";
// link_status bit 0 = back-end port 0, bit 1 = back-end port 1
constexpr uint8_t kAllLinksUp = 0x3;

std::string to_hex_str(uint64_t value) {
  char buf[24];
  snprintf(buf, sizeof(buf), "0x%llx", static_cast<unsigned long long>(value));
  return buf;
}

const char* mpn_mode_str(int mode) {
  switch (mode) {
    case MPCTL_MPN_MODE_PMEM:
      return "pmem";
    case MPCTL_MPN_MODE_DEVDAX:
      return "devdax";
    case MPCTL_MPN_MODE_NUMA:
      return "numa";
    default:
      return "unknown";
  }
}

const char* mpn_location_str(int location) {
  switch (location) {
    case MPCTL_MPN_LOCAL:
      return "local";
    case MPCTL_MPN_REMOTE:
      return "remote";
    default:
      return "all";
  }
}

uint64_t mpn_capacity_MB(const mpctl_mpn& mpn) {
  // prefer the usable size after the namespace label
  return mpn.size ? mpn.size / kMiB : static_cast<uint64_t>(mpn.size_gb) * 1024;
}

/**
 * @brief Returns the CMM-MP entry of cxl_dev_id_map.json, if present.
 */
const DevJsonHints* find_cmmmp_hints() {
  const DevTypeMap* dt_map = find_dev_type_map();
  if (!dt_map) {
    return nullptr;
  }
  for (const auto& [key, hint] : *dt_map) {
    if (hint.vendor_device_type == kCmmMpDeviceType) {
      return &hint;
    }
  }
  return nullptr;
}

DevStaticInfo base_static_info(uint64_t d_id, const std::string& type) {
  DevStaticInfo sinfo;
  sinfo.device_id = d_id;
  sinfo.manufacturer = "samsung";
  sinfo.serial_number = 0;
  sinfo.vendor_device_type = type;
  sinfo.cxl_device_type = "Type3";
  sinfo.device_index = 0;
  return sinfo;
}

}  // namespace

uint64_t cmmmp_dev_id(uint16_t kind, uint16_t index) {
  return (static_cast<uint64_t>(kCmmMpVendorId) << 32) |
         (static_cast<uint64_t>(kind) << 16) | index;
}

MpKind cmmmp_kind(uint64_t d_id) {
  if (((d_id >> 32) & 0xFFFF) != kCmmMpVendorId) {
    return MpKind::UNKNOWN;
  }
  switch ((d_id >> 16) & 0xFFFF) {
    case kCmmMpKindPool:
      return MpKind::POOL;
    case kCmmMpKindMpDev:
      return MpKind::MPDEV;
    case kCmmMpKindMpn:
      return MpKind::MPN;
    default:
      return MpKind::UNKNOWN;
  }
}

uint16_t cmmmp_index(uint64_t d_id) { return d_id & 0xFFFF; }

/**
 * @brief DevCMMMP constructor.
 */
DevCMMMP::DevCMMMP() { LOG(level_E::INFO, "DevCMMMP adapter constructed"); }

/**
 * @brief DevCMMMP destructor.
 */
DevCMMMP::~DevCMMMP() {
  std::lock_guard<std::mutex> lock(mp_lock_);
  close_ctx();
  LOG(level_E::INFO, "DevCMMMP adapter destroyed");
}

int DevCMMMP::map_rc(int mpctl_rc) {
  switch (mpctl_rc) {
    case MPCTL_RC_SUCCESS:
      return 0;
    case MPCTL_RC_NO_MP_FOUND:
      return -ENODEV;
    case MPCTL_RC_POOL_NOT_READY:
      return -EAGAIN;
    case MPCTL_RC_MPN_NOT_FOUND:
      return -ENOENT;
    default:
      return -EIO;
  }
}

int DevCMMMP::ensure_ctx() const {
  if (ctx_) {
    return 0;
  }

  mpctl_ctx* ctx = nullptr;
  int rc = mpctl_init(&ctx);
  if (rc == MPCTL_RC_SUCCESS && ctx) {
    ctx_ = ctx;
    LOG(level_E::INFO, "DevCMMMP: libmpctl context initialized");
    return 0;
  }

  // on failure mpctl_init releases its own context
  if (rc == MPCTL_RC_NO_MP_FOUND) {
    LOG(level_E::INFO, "DevCMMMP: no CMM-MP device found");
  } else {
    LOG(level_E::ERROR,
        "DevCMMMP: mpctl_init failed, rc=" + std::to_string(rc));
  }
  return rc == MPCTL_RC_SUCCESS ? -EIO : map_rc(rc);
}

void DevCMMMP::close_ctx() const {
  if (ctx_) {
    mpctl_close(ctx_);
    ctx_ = nullptr;
    LOG(level_E::DEBUG, "DevCMMMP: libmpctl context released");
  }
}

void DevCMMMP::setup_pool_if_configured() {
  const mpctl_pool* pool = mpctl_pool_get_info(ctx_);
  if (!pool || pool->ready) {
    return;
  }

  if (!cfg_.auto_pool_setup) {
    LOG(level_E::INFO,
        "DevCMMMP: memory pool not ready and cmmmp.auto_pool_setup is "
        "disabled");
    return;
  }

  LOG(level_E::INFO, "DevCMMMP: memory pool not ready, running pool setup");
  int rc = mpctl_host_init_discovery(ctx_);
  if (rc != MPCTL_RC_SUCCESS) {
    LOG(level_E::ERROR,
        "DevCMMMP: mpctl_host_init_discovery failed, rc=" + std::to_string(rc));
    return;
  }
  rc = mpctl_pool_create(ctx_);
  if (rc != MPCTL_RC_SUCCESS) {
    LOG(level_E::ERROR,
        "DevCMMMP: mpctl_pool_create failed, rc=" + std::to_string(rc));
    return;
  }

  // MPNs of the new pool are only discovered by mpctl_init
  close_ctx();
  ensure_ctx();
}

DevInfo DevCMMMP::build_pool_info(const mpctl_pool& pool) const {
  DevInfo info;
  DevStaticInfo& sinfo = info.static_info;
  sinfo =
      base_static_info(cmmmp_dev_id(kCmmMpKindPool, 0), kCmmMpPoolDeviceType);
  sinfo.location = "pool";
  sinfo.total_capacity_MB = static_cast<uint64_t>(pool.size_gb) * 1024;
  sinfo.domain_type = "CMM-MP pool";
  sinfo.connection_type = kBackendConnection;
  sinfo.mode_discovered =
      pool.host_init_disc ? "host-initiated" : "device-initiated";

  auto& vs = sinfo.capabilities.vendor_specific;
  vs["disc_mode"] = std::to_string(pool.disc_mode);
  vs["host_init_disc"] = pool.host_init_disc ? "true" : "false";
  vs["mpdev_count"] = std::to_string(pool.mpdev_count);
  vs["unpooled_mpdev_count"] = std::to_string(pool.unpooled_mpdev_count);
  vs["mpn_count"] = std::to_string(pool.mpn_count);

  // pool capacity that is not attached to this host
  uint64_t available_mb = 0;
  for (unsigned int id = 0; id < pool.mpn_count; ++id) {
    const mpctl_mpn* mpn = mpctl_mpn_get_info(ctx_, id);
    if (mpn && !mpn->status) {
      available_mb += mpn_capacity_MB(*mpn);
    }
  }

  info.status = pool.ready ? "Ready" : "NotReady";
  info.numa_node = -1;
  info.available_capacity_MB = available_mb;
  return info;
}

DevInfo DevCMMMP::build_mpdev_info(const mpctl_mpdev& mpdev,
                                   uint64_t d_id) const {
  DevInfo info;
  DevStaticInfo& sinfo = info.static_info;
  sinfo = base_static_info(d_id, kCmmMpDeviceType);
  sinfo.serial_number = mpdev.chip_id;
  // libmpctl handle used for subsequent mpctl_mpdev_get_info() calls
  sinfo.device_index = mpdev.id;

  char fw[48];
  snprintf(fw, sizeof(fw), "fpga 0x%04x / fw %u", mpdev.fpga_ver,
           static_cast<unsigned int>(mpdev.fw_ver));
  sinfo.fw_revision = fw;
  sinfo.total_capacity_MB = static_cast<uint64_t>(mpdev.size_gb) * 1024;
  sinfo.location = mpdev.local ? "local" : "remote";
  sinfo.connection_type = mpdev.local ? "CXL.mem" : kBackendConnection;
  sinfo.domain_type = "CMM-MP pool";

  auto& vs = sinfo.capabilities.vendor_specific;
  vs["parent_id"] = to_hex_str(cmmmp_dev_id(kCmmMpKindPool, 0));
  vs["mpctl_id"] = std::to_string(mpdev.id);
  vs["slot_id"] = std::to_string(mpdev.slot_id);
  vs["chip_id"] = to_hex_str(mpdev.chip_id);
  vs["eth_port0"] = (mpdev.link_status & 0x1) ? "up" : "down";
  vs["eth_port1"] = (mpdev.link_status & 0x2) ? "up" : "down";
  vs["fpga_temp_C"] = std::to_string(mpdev.fpga_temp);

  // link / QoS hints only describe the local CXL front-end
  const DevJsonHints* hints = mpdev.local ? find_cmmmp_hints() : nullptr;
  if (hints) {
    sinfo.link_speed_GT_s = hints->lane_speed_GT_s;
    sinfo.link_width = hints->lane_width;
    sinfo.protocol = hints->protocol;
    sinfo.port_type = hints->port_type;
    sinfo.advertised_qos = hints->advertised_qos;
    sinfo.bw_interval_sec = hints->bw_interval_sec;
  }

  std::string status = mpdev.status ? "Pooled" : "Unpooled";
  if ((mpdev.link_status & kAllLinksUp) != kAllLinksUp) {
    status += ", Degraded";
  }
  if (mpdev.fpga_temp > cfg_.fpga_temp_warn_C) {
    status += ", Warning";
  }
  info.status = status;
  info.numa_node = -1;
  // MP device capacity is consumed through MPNs
  info.available_capacity_MB = 0;
  return info;
}

DevInfo DevCMMMP::build_mpn_info(const mpctl_mpn& mpn) const {
  DevInfo info;
  DevStaticInfo& sinfo = info.static_info;
  sinfo = base_static_info(cmmmp_dev_id(kCmmMpKindMpn, mpn.id),
                           kCmmMpMpnDeviceType);
  sinfo.device_index = mpn.id;
  sinfo.domain_id = mpn.region_id;
  sinfo.domain_type = "CXL region";
  sinfo.connection_type = "CXL.mem";
  sinfo.total_capacity_MB = mpn_capacity_MB(mpn);
  sinfo.mode_discovered = mpn_mode_str(mpn.mode);
  if (mpn.mode == MPCTL_MPN_MODE_DEVDAX && mpn.dax_devname[0] != '\0') {
    sinfo.location =
        std::string(mpn.dax_devname, strnlen(mpn.dax_devname, STR_MAX));
  } else {
    sinfo.location = "region" + std::to_string(mpn.region_id);
  }

  auto& vs = sinfo.capabilities.vendor_specific;
  vs["parent_id"] = to_hex_str(cmmmp_dev_id(kCmmMpKindPool, 0));
  vs["hpa"] = to_hex_str(mpn.host_phys_addr);
  vs["mpn_location"] = mpn_location_str(mpn.location);
  vs["slot_id"] = std::to_string(mpn.slot_id);
  vs["region_id"] = std::to_string(mpn.region_id);

  info.status = mpn.status ? "Online" : "Offline";
  info.numa_node = mpn.mode == MPCTL_MPN_MODE_NUMA ? mpn.namespace_numa : -1;

  if (!mpn.status) {
    info.available_capacity_MB = sinfo.total_capacity_MB;
  } else if (mpn.mode == MPCTL_MPN_MODE_NUMA && mpn.namespace_numa >= 0) {
    uint64_t total_mb = 0, free_mb = 0;
    if (get_numa_memory_info(mpn.namespace_numa, total_mb, free_mb)) {
      info.available_capacity_MB = std::min(free_mb, sinfo.total_capacity_MB);
    }
  } else {
    // devdax: the whole MPN is handed to the dax consumer
    info.available_capacity_MB = 0;
  }
  return info;
}

bool DevCMMMP::refresh_device(const sc_id& sid, DevInfo& info) const {
  if (!ctx_) {
    return false;
  }

  uint64_t d_id = sid.get_sc_id();
  switch (cmmmp_kind(d_id)) {
    case MpKind::POOL: {
      const mpctl_pool* pool = mpctl_pool_get_info(ctx_);
      if (!pool) {
        return false;
      }
      mpctl_pool copy = *pool;
      info = build_pool_info(copy);
      return true;
    }
    case MpKind::MPDEV: {
      const mpctl_mpdev* mpdev = mpctl_mpdev_get_info(
          ctx_, static_cast<unsigned int>(info.static_info.device_index));
      // the handle may refer to another device after a context re-init
      if (!mpdev || mpdev->chip_id != info.static_info.serial_number) {
        return false;
      }
      mpctl_mpdev copy = *mpdev;
      info = build_mpdev_info(copy, d_id);
      return true;
    }
    case MpKind::MPN: {
      const mpctl_mpn* mpn = mpctl_mpn_get_info(ctx_, cmmmp_index(d_id));
      if (!mpn) {
        return false;
      }
      mpctl_mpn copy = *mpn;
      info = build_mpn_info(copy);
      return true;
    }
    default:
      return false;
  }
}

DevInfo DevCMMMP::refresh_cached(const sc_id& sid) const {
  auto it = device_map_.find(sid);
  if (it == device_map_.end()) {
    return DevInfo{};
  }

  // get existing device
  sc_device& dev = const_cast<sc_device&>(it->second);
  DevInfo info = dev.d_get_info();

  if (refresh_device(sid, info)) {
    dev.d_set_static_info(info.static_info);
  } else {
    LOG(level_E::WARN, "DevCMMMP: no libmpctl info for device " +
                           to_hex_str(sid.get_sc_id()) +
                           ", returning cached info");
    info.status = "Unavailable";
  }
  dev.d_set_dynamic_info(info);
  return info;
}

/**
 * @brief Returns all discovered devices.
 */
std::vector<sc_device> DevCMMMP::list_devices() const {
  LOG(level_E::INFO, "DevCMMMP::list_devices() called");
  std::lock_guard<std::mutex> lock(mp_lock_);
  std::vector<sc_device> result;
  for (const auto& [id, dev] : device_map_) {
    result.push_back(dev);
  }
  LOG(level_E::DEBUG, "DevCMMMP::list_devices returned " +
                          std::to_string(result.size()) + " devices");
  return result;
}

/**
 * @brief Returns a specific device object from internal map.
 */
sc_device DevCMMMP::get_device_object(const sc_id& sid) const {
  LOG(level_E::DEBUG, "DevCMMMP::get_device_object called");
  std::lock_guard<std::mutex> lock(mp_lock_);
  auto it = device_map_.find(sid);
  return it != device_map_.end() ? it->second : sc_device{};
}

/**
 * @brief Returns refreshed DevInfo for a given device ID.
 */
DevInfo DevCMMMP::get_device_info(const sc_id& sid) const {
  LOG(level_E::INFO, "DevCMMMP::get_device_info called");
  std::lock_guard<std::mutex> lock(mp_lock_);
  return refresh_cached(sid);
}

/**
 * @brief Returns StatInfo for a given device ID.
 */
StatInfo DevCMMMP::get_device_stats(const sc_id& sid) const {
  LOG(level_E::INFO, "DevCMMMP::get_device_stats called");
  DevInfo info = get_device_info(sid);

  StatInfo stats;
  stats.device_id = info.static_info.device_id;
  stats.protocol = info.static_info.protocol;
  stats.port_type = info.static_info.port_type;
  stats.status = info.status;

  stats.total_memory_MB = info.static_info.total_capacity_MB;
  stats.available_memory_MB = info.available_capacity_MB;
  stats.used_memory_MB = stats.total_memory_MB > stats.available_memory_MB
                             ? stats.total_memory_MB - stats.available_memory_MB
                             : 0;

  // theoretical one-direction bandwidth from link hints, as for CMM-H
  stats.total_bandwidth_MBps =
      info.static_info.link_speed_GT_s * info.static_info.link_width * 125;

  // libmpctl v0.3 exposes no performance or error counters
  stats.used_bandwidth_Bps = 0;
  stats.rw_errors = 0;
  stats.latency_us = 0;

  if (cmmmp_kind(sid.get_sc_id()) == MpKind::MPDEV &&
      info.status != "Unavailable") {
    const auto& vs = info.static_info.capabilities.vendor_specific;
    auto it = vs.find("fpga_temp_C");
    if (it != vs.end()) {
      // reported as fpga_temp_in_F, matching the CMM-H convention
      cmmh_stat_sensor_t sensor{};
      sensor.status = CMMH_STAT_RC_SUCCESS;
      sensor.fpga_temp = std::stoul(it->second) * 9 / 5 + 32;
      stats.sensor_stats = sensor;
    }
  }

  LOG(level_E::INFO, "DevCMMMP::get_device_stats completed");
  return stats;
}

void DevCMMMP::upsert_device(DeviceManager& mgr, const sc_id& sid,
                             const DevInfo& info, const std::string& name) {
  sc_device dev(sid.get_sc_id(), name, info.static_info.total_capacity_MB, 0);
  dev.d_set_static_info(info.static_info);
  dev.d_set_dynamic_info(info);

  auto it = device_map_.find(sid);
  if (it != device_map_.end()) {
    it->second = dev;
    return;
  }
  device_map_.emplace(sid, dev);
  mgr.register_device(sid, this);
}

/**
 * @brief Enumerate the memory pool, MP devices and MPNs through libmpctl.
 *
 * The pool is registered first, then every MP device (pooled and unpooled,
 * local and, if enabled, remote) and every MPN. Already-known devices are
 * refreshed but not registered again.
 *
 * @param mgr Reference to the DeviceManager used to register discovered
 * devices.
 */
void DevCMMMP::discover_devices(DeviceManager& mgr) {
  LOG(level_E::INFO, "DevCMMMP::discover_devices started");
  std::lock_guard<std::mutex> lock(mp_lock_);

  if (!cfg_.enabled) {
    LOG(level_E::INFO, "DevCMMMP: disabled in cxl.conf, skipping discovery");
    return;
  }
  if (ensure_ctx() != 0) {
    return;
  }
  setup_pool_if_configured();
  if (!ctx_) {
    return;
  }

  const mpctl_pool* pool_info = mpctl_pool_get_info(ctx_);
  if (!pool_info) {
    LOG(level_E::ERROR, "DevCMMMP: mpctl_pool_get_info failed");
    return;
  }
  mpctl_pool pool = *pool_info;
  upsert_device(mgr, sc_id(cmmmp_dev_id(kCmmMpKindPool, 0)),
                build_pool_info(pool), "cmmmp-pool");

  // MP device ids cover pooled and unpooled devices
  std::unordered_set<uint16_t> used_slots;
  unsigned int mpdev_total = pool.mpdev_count + pool.unpooled_mpdev_count;
  for (unsigned int id = 0; id < mpdev_total; ++id) {
    const mpctl_mpdev* info = mpctl_mpdev_get_info(ctx_, id);
    if (!info) {
      LOG(level_E::WARN,
          "DevCMMMP: no info for MP device " + std::to_string(id));
      continue;
    }
    mpctl_mpdev mpdev = *info;
    if (!mpdev.local && !cfg_.expose_remote_mpdevs) {
      continue;
    }

    uint16_t index = mpdev.slot_id;
    if (!used_slots.insert(index).second) {
      index = kCmmMpIndexFallback | (id & 0x7FFF);
      LOG(level_E::WARN, "DevCMMMP: slot_id " + std::to_string(mpdev.slot_id) +
                             " already in use, MP device " +
                             std::to_string(id) + " uses index " +
                             std::to_string(index));
    }
    sc_id sid(cmmmp_dev_id(kCmmMpKindMpDev, index));
    upsert_device(mgr, sid, build_mpdev_info(mpdev, sid.get_sc_id()),
                  "cmmmp-mpdev");
  }

  for (unsigned int id = 0; id < pool.mpn_count; ++id) {
    const mpctl_mpn* info = mpctl_mpn_get_info(ctx_, id);
    if (!info) {
      LOG(level_E::WARN, "DevCMMMP: no info for MPN " + std::to_string(id));
      continue;
    }
    mpctl_mpn mpn = *info;
    upsert_device(mgr, sc_id(cmmmp_dev_id(kCmmMpKindMpn, mpn.id)),
                  build_mpn_info(mpn), "cmmmp-mpn");
  }

  LOG(level_E::INFO, "DevCMMMP::discover_devices completed with " +
                         std::to_string(device_map_.size()) + " devices");
}

int DevCMMMP::validate_mpn_op(const sc_id& sid, const mpctl_mpn** mpn) const {
  if (cmmmp_kind(sid.get_sc_id()) != MpKind::MPN) {
    return -EINVAL;
  }
  int rc = ensure_ctx();
  if (rc != 0) {
    return rc;
  }
  const mpctl_pool* pool = mpctl_pool_get_info(ctx_);
  if (!pool || !pool->ready) {
    return -EAGAIN;
  }
  const mpctl_mpn* info =
      mpctl_mpn_get_info(ctx_, cmmmp_index(sid.get_sc_id()));
  if (!info) {
    return -ENOENT;
  }
  *mpn = info;
  return 0;
}

/**
 * @brief Onlines an MPN as NUMA memory or enables it as a devdax device.
 */
int DevCMMMP::attach_memory(const sc_id& sid, const AttachParams& params) {
  LOG(level_E::INFO,
      "DevCMMMP::attach_memory called for " + to_hex_str(sid.get_sc_id()));
  std::lock_guard<std::mutex> lock(mp_lock_);

  const mpctl_mpn* mpn = nullptr;
  int rc = validate_mpn_op(sid, &mpn);
  if (rc != 0) {
    LOG(level_E::WARN,
        "DevCMMMP::attach_memory rejected, rc=" + std::to_string(rc));
    return rc;
  }

  const std::string& mode =
      params.mode.empty() ? cfg_.default_attach_mode : params.mode;
  if (mode != "numa" && mode != "devdax") {
    LOG(level_E::WARN, "DevCMMMP::attach_memory: invalid mode " + mode);
    return -EINVAL;
  }
  if (mpn->status) {
    LOG(level_E::WARN, "DevCMMMP::attach_memory: MPN " +
                           std::to_string(mpn->id) + " is already online");
    return -EBUSY;
  }

  unsigned int mpn_id = mpn->id;
  int lib_rc = mode == "numa" ? mpctl_mpn_online(ctx_, mpn_id)
                              : mpctl_mpn_enable_dax(ctx_, mpn_id);
  refresh_cached(sid);

  rc = map_rc(lib_rc);
  if (rc != 0) {
    LOG(level_E::ERROR, "DevCMMMP::attach_memory: MPN " +
                            std::to_string(mpn_id) + " (" + mode +
                            ") failed, rc=" + std::to_string(lib_rc));
  } else {
    LOG(level_E::INFO, "DevCMMMP::attach_memory: MPN " +
                           std::to_string(mpn_id) + " attached as " + mode);
  }
  return rc;
}

/**
 * @brief Offlines an MPN (NUMA or devdax) on the local server.
 */
int DevCMMMP::detach_memory(const sc_id& sid) {
  LOG(level_E::INFO,
      "DevCMMMP::detach_memory called for " + to_hex_str(sid.get_sc_id()));
  std::lock_guard<std::mutex> lock(mp_lock_);

  const mpctl_mpn* mpn = nullptr;
  int rc = validate_mpn_op(sid, &mpn);
  if (rc != 0) {
    LOG(level_E::WARN,
        "DevCMMMP::detach_memory rejected, rc=" + std::to_string(rc));
    return rc;
  }
  if (!mpn->status) {
    LOG(level_E::WARN, "DevCMMMP::detach_memory: MPN " +
                           std::to_string(mpn->id) + " is already offline");
    return -EBUSY;
  }

  unsigned int mpn_id = mpn->id;
  int lib_rc = mpctl_mpn_offline(ctx_, mpn_id);
  refresh_cached(sid);

  rc = map_rc(lib_rc);
  if (rc != 0) {
    LOG(level_E::ERROR, "DevCMMMP::detach_memory: MPN " +
                            std::to_string(mpn_id) +
                            " failed, rc=" + std::to_string(lib_rc));
  } else {
    LOG(level_E::INFO,
        "DevCMMMP::detach_memory: MPN " + std::to_string(mpn_id) + " offline");
  }
  return rc;
}

/**
 * @brief Runs a pool-level libmpctl operation.
 */
int DevCMMMP::pool_operation(PoolOp op, const PoolOpParams& params) {
  LOG(level_E::INFO, "DevCMMMP::pool_operation called");
  std::lock_guard<std::mutex> lock(mp_lock_);

  int rc = ensure_ctx();
  if (rc != 0) {
    return rc;
  }

  int lib_rc;
  switch (op) {
    case PoolOp::HOST_INIT_DISCOVERY:
      lib_rc = mpctl_host_init_discovery(ctx_);
      break;
    case PoolOp::CREATE:
      lib_rc = mpctl_pool_create(ctx_);
      break;
    case PoolOp::ADD:
      lib_rc = mpctl_pool_add(ctx_, params.id);
      break;
    default:
      return -EINVAL;
  }

  rc = map_rc(lib_rc);
  if (rc != 0) {
    LOG(level_E::ERROR,
        "DevCMMMP::pool_operation failed, rc=" + std::to_string(lib_rc));
    return rc;
  }

  if (op != PoolOp::HOST_INIT_DISCOVERY) {
    // pool membership changes are only discovered by mpctl_init
    close_ctx();
    rc = ensure_ctx();
  }
  return rc;
}

/**
 * @brief Loads the "cmmmp" section of a cxl.conf style JSON file.
 */
int DevCMMMP::load_config(const std::string& filepath) {
  json_error_t error;
  json_t* root = json_load_file(filepath.c_str(), 0, &error);
  if (!root) {
    LOG(level_E::WARN, "DevCMMMP: unable to load " + filepath +
                           ", using default configuration");
    return -ENOENT;
  }

  json_t* section = json_object_get(root, "cmmmp");
  if (!json_is_object(section)) {
    LOG(level_E::INFO, "DevCMMMP: no \"cmmmp\" section in " + filepath +
                           ", using default configuration");
    json_decref(root);
    return 0;
  }

  std::lock_guard<std::mutex> lock(mp_lock_);
  json_t* value = json_object_get(section, "enabled");
  if (json_is_boolean(value)) {
    cfg_.enabled = json_is_true(value);
  }
  value = json_object_get(section, "auto_pool_setup");
  if (json_is_boolean(value)) {
    cfg_.auto_pool_setup = json_is_true(value);
  }
  value = json_object_get(section, "expose_remote_mpdevs");
  if (json_is_boolean(value)) {
    cfg_.expose_remote_mpdevs = json_is_true(value);
  }
  value = json_object_get(section, "default_attach_mode");
  if (json_is_string(value)) {
    std::string mode = json_string_value(value);
    if (mode == "numa" || mode == "devdax") {
      cfg_.default_attach_mode = mode;
    } else {
      LOG(level_E::WARN,
          "DevCMMMP: ignoring invalid default_attach_mode " + mode);
    }
  }
  value = json_object_get(section, "fpga_temp_warn_C");
  if (json_is_integer(value)) {
    cfg_.fpga_temp_warn_C = static_cast<int>(json_integer_value(value));
  }
  json_decref(root);

  LOG(level_E::INFO,
      "DevCMMMP: configuration loaded (enabled=" +
          std::to_string(cfg_.enabled) +
          ", auto_pool_setup=" + std::to_string(cfg_.auto_pool_setup) +
          ", default_attach_mode=" + cfg_.default_attach_mode +
          ", expose_remote_mpdevs=" +
          std::to_string(cfg_.expose_remote_mpdevs) +
          ", fpga_temp_warn_C=" + std::to_string(cfg_.fpga_temp_warn_C) + ")");
  return 0;
}

/**
 * @brief Loads adapter configuration. Hardware is not touched here.
 * @return Always 0; the defaults are used if cxl.conf has no "cmmmp" section.
 */
int DevCMMMP::setup_info() {
  LOG(level_E::INFO, "DevCMMMP::setup_info called");
  load_config(CXL_CONF_FILE);
  return 0;
}

void register_cmmmp_adapter(DeviceManager& mgr) {
  LOG(level_E::INFO, "CMM-MP plugin registering with DeviceManager");
  static DevCMMMP* adapter = new DevCMMMP();
  adapter->setup_info();
  mgr.registerAdapter("cmmmp", adapter);
  LOG(level_E::INFO, "DevCMMMP plugin registered successfully");
}
