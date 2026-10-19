#ifndef DEV_CMMMP_H
#define DEV_CMMMP_H

#include <mutex>
#include <string>
#include <string_view>
#include <unordered_map>

#include "libmpctl.h"  // C++ ABI - do NOT wrap in extern "C"
#include "sc_cxl_dev_adapter.h"
#include "sc_logger.h"

/** Configuration file holding the "cmmmp" section */
inline constexpr std::string_view kCmmMpConfFile = "cxl.conf";

/**
 * @brief CMM-MP device ID layout.
 *
 * DeviceManager resolves 48-bit numeric device IDs. CMM-H / CMM-D derive them
 * from PCI identity via generate_dev_id(vendor, device, bus). Remote MP
 * devices and MPNs have no local PCI function, so DevCMMMP uses the same field
 * layout with reserved kind codes in place of the PCI device ID:
 *
 *   d_id = [47:32] vendor 0x1E98 | [31:16] CMM-MP kind code | [15:0] index
 *
 * The kind codes are provisional until they are formally reserved; they are
 * chosen from a range that is not used by Samsung PCI device IDs (e.g. CMM-H
 * 0x0DDB), so they cannot collide with PCI-derived IDs.
 */
inline constexpr uint16_t kCmmMpVendorId = 0x1E98;
inline constexpr uint16_t kCmmMpKindPool = 0xFF00;
inline constexpr uint16_t kCmmMpKindMpDev = 0xFF01;
inline constexpr uint16_t kCmmMpKindMpn = 0xFF02;

/** Index flag used when an MP device slot_id collides with another device */
inline constexpr uint16_t kCmmMpIndexFallback = 0x8000;

/**
 * @brief Kind of libmpctl entity represented by a device ID.
 */
enum class MpKind { POOL, MPDEV, MPN, UNKNOWN };

/**
 * @brief Encodes a CMM-MP device ID.
 * @param kind Kind code (kCmmMpKindPool, kCmmMpKindMpDev or kCmmMpKindMpn).
 * @param index Entity index (0 for the pool, slot_id for MP devices, MPN id).
 * @return 48-bit device ID.
 */
uint64_t cmmmp_dev_id(uint16_t kind, uint16_t index);

/**
 * @brief Decodes the entity kind of a CMM-MP device ID.
 */
MpKind cmmmp_kind(uint64_t d_id);

/**
 * @brief Decodes the entity index of a CMM-MP device ID.
 */
uint16_t cmmmp_index(uint64_t d_id);

/**
 * @brief Adapter configuration, read from the "cmmmp" section of cxl.conf.
 */
struct CmmMpConfig {
  // Register CMM-MP devices at all
  bool enabled = true;
  // Run host-initiated discovery + pool create at discovery when the pool is
  // not ready. Changes pool-wide state shared with other servers.
  bool auto_pool_setup = false;
  // Mode used by attach_memory() when none is requested ("numa" | "devdax")
  std::string default_attach_mode = "numa";
  // Register remote MP devices for observability
  bool expose_remote_mpdevs = true;
  // FPGA temperature (C) above which an MP device reports "Warning"
  int fpga_temp_warn_C = 85;
};

/**
 * @class DevCMMMP
 * @brief CXL Adapter implementation for CMM-MP (multi pathing CXL memory
 * module) devices.
 *
 * DevCMMMP is a plugin that inherits from CXLDeviceAdapter and wraps
 * libmpctl. It registers three kinds of devices:
 * - POOL: the memory pool visible to this server (one per server),
 * - MPDEV: each local or remote MP device, used for observability,
 * - MPN: each memory pool node, the unit that is attached to the host as a
 *   NUMA node or devdax device.
 *
 * MP devices and MPNs record the pool device ID in
 * capabilities.vendor_specific["parent_id"].
 *
 * libmpctl uses no locking, so every library call is serialised by one
 * adapter-level mutex. Structures returned by mpctl_*_get_info() point into
 * the library context; they are copied while the lock is held and never
 * freed by the adapter.
 */
class DevCMMMP : public CXLDeviceAdapter {
 public:
  /**
   * @brief Constructor. Does not touch hardware; the libmpctl context is
   * created lazily on first discovery.
   */
  DevCMMMP();

  /**
   * @brief Destructor — releases the libmpctl context.
   */
  ~DevCMMMP() override;

  /** The adapter owns the libmpctl context and is not copyable or movable */
  DevCMMMP(const DevCMMMP&) = delete;
  DevCMMMP& operator=(const DevCMMMP&) = delete;
  DevCMMMP(DevCMMMP&&) = delete;
  DevCMMMP& operator=(DevCMMMP&&) = delete;

  /**
   * @brief Returns all POOL, MPDEV and MPN devices discovered by this adapter.
   */
  std::vector<sc_device> list_devices() const override;

  /**
   * @brief Retrieves a specific device from the internal map.
   * @return The sc_device object if found, otherwise a default sc_device.
   */
  sc_device get_device_object(const sc_id& sid) const override;

  /**
   * @brief Returns refreshed DevInfo for the given device ID.
   *
   * The entity kind is decoded from the ID and the matching
   * mpctl_*_get_info() call refreshes the dynamic fields. If the library
   * returns no information, the cached static info is returned with status
   * "Unavailable".
   */
  DevInfo get_device_info(const sc_id& sid) const override;

  /**
   * @brief Returns runtime statistics built from refreshed device info.
   */
  StatInfo get_device_stats(const sc_id& sid) const override;

  /**
   * @brief Enumerates the pool, MP devices and MPNs and registers new ones.
   *
   * Creates the libmpctl context on first use. MPCTL_RC_NO_MP_FOUND results
   * in zero devices. Already-known devices are not registered again, but
   * their cached info is refreshed.
   */
  void discover_devices(DeviceManager& mgr) override;

  /**
   * @brief Loads the "cmmmp" section of cxl.conf.
   * @return 0 on success (defaults are used if the section is missing).
   */
  int setup_info() override;

  /**
   * @brief Attaches an MPN to the local host as a NUMA node or devdax device.
   * @return 0 on success, -EINVAL for a non-MPN device or unknown mode,
   * -ENOENT if the MPN is not found, -EAGAIN if the pool is not ready,
   * -EBUSY if the MPN is already online, -EIO on library error.
   */
  int attach_memory(const sc_id& sid, const AttachParams& params) override;

  /**
   * @brief Offlines an MPN on the local host.
   * @return 0 on success, -EINVAL for a non-MPN device, -ENOENT if the MPN is
   * not found, -EAGAIN if the pool is not ready, -EBUSY if the MPN is
   * already offline, -EIO on library error.
   */
  int detach_memory(const sc_id& sid) override;

  /**
   * @brief Runs host-initiated discovery, pool creation or hot add.
   * @return 0 on success, negative POSIX error code on failure.
   */
  int pool_operation(PoolOp op, const PoolOpParams& params) override;

  /**
   * @brief Loads adapter configuration from a cxl.conf style JSON file.
   * @param filepath Path to the configuration file.
   * @return 0 on success, -ENOENT if the file cannot be loaded (defaults are
   * kept).
   */
  int load_config(const std::string& filepath);

  /**
   * @brief Returns the active adapter configuration.
   */
  const CmmMpConfig& config() const { return cfg_; }

  /**
   * @brief Maps a libmpctl return code to a negative POSIX error code.
   */
  static int map_rc(int mpctl_rc);

 protected:
  /** Replaces the adapter configuration, for derived classes and tests. */
  void set_config(const CmmMpConfig& cfg) {
    std::scoped_lock lock(mp_lock_);
    cfg_ = cfg;
  }

  /** Returns true if the libmpctl context has been created. */
  bool has_ctx() const { return ctx_ != nullptr; }

 private:
  /** Creates the libmpctl context if needed. Caller holds mp_lock_. */
  int ensure_ctx() const;

  /** Releases the libmpctl context. Caller holds mp_lock_. */
  void close_ctx() const;

  /** Runs pool setup if enabled and the pool is not ready. Caller holds
   * mp_lock_. */
  void setup_pool_if_configured() const;

  /** Builds DevInfo for the pool. Caller holds mp_lock_. */
  DevInfo build_pool_info(const mpctl_pool& pool) const;

  /** Builds DevInfo for an MP device. Caller holds mp_lock_. */
  DevInfo build_mpdev_info(const mpctl_mpdev& mpdev, uint64_t d_id) const;

  /** Builds DevInfo for an MPN. Caller holds mp_lock_. */
  DevInfo build_mpn_info(const mpctl_mpn& mpn) const;

  /** Re-reads the library state of a device. Caller holds mp_lock_. */
  bool refresh_device(const sc_id& sid, DevInfo& info) const;

  /** Refreshes the cached entry of a device and returns its info, or a
   * default DevInfo if unknown. Caller holds mp_lock_. */
  DevInfo refresh_cached(const sc_id& sid) const;

  /** Inserts or refreshes a device and registers it if it is new. */
  void upsert_device(DeviceManager& mgr, const sc_id& sid, const DevInfo& info,
                     std::string_view name);

  /** Calls the libmpctl function for a pool operation. Returns the mpctl_rc,
   * or -EINVAL for an unknown operation. Caller holds mp_lock_. */
  int run_pool_op(PoolOp op, const PoolOpParams& params) const;

  /** Validates that sid is an MPN of a ready pool. Caller holds mp_lock_. */
  int validate_mpn_op(const sc_id& sid, const mpctl_mpn** mpn) const;

  /** Discovered devices; refreshed by the const info / stats queries */
  mutable std::unordered_map<sc_id, sc_device, hash_sc_id> devices_;

  /** Serialises all libmpctl calls (the library is not thread-safe) */
  mutable std::mutex mp_lock_;

  /** libmpctl context, created lazily */
  mutable mpctl_ctx* ctx_ = nullptr;

  /** Adapter configuration */
  CmmMpConfig cfg_;
};

/**
 * @brief Creates the DevCMMMP singleton, loads its configuration and
 * registers it with the DeviceManager under the name "cmmmp".
 *
 * Called by the plugin entry point register_plugin() (cmmmp_plugin.cc).
 *
 * @param mgr Reference to DeviceManager for adapter registration.
 */
void register_cmmmp_adapter(DeviceManager& mgr);

/**
 * @brief Plugin entry point called by PluginManager.
 *
 * Defined in cmmmp_plugin.cc, so that unit tests linking all adapter sources
 * do not get a second register_plugin() definition.
 *
 * @param mgr Reference to DeviceManager for adapter registration.
 */
extern "C" void register_plugin(DeviceManager& mgr);

#endif
