#include "mock_libmpctl.h"

#include <cstdio>

struct mpctl_ctx {
  int unused;
};

namespace mock_mpctl {

State& state() {
  static State s;
  return s;
}

void reset() {
  state() = State{};
  state().pool.ready = 1;
}

mpctl_mpdev& add_mpdev(unsigned int slot_id, bool local, bool pooled,
                       uint16_t size_gb, uint32_t chip_id) {
  State& s = state();
  mpctl_mpdev dev{};
  dev.id = static_cast<unsigned int>(s.mpdevs.size());
  dev.fpga_ver = 0x0103;
  dev.fw_ver = 7;
  dev.chip_id = chip_id;
  dev.local = local;
  dev.size_gb = size_gb;
  dev.slot_id = static_cast<uint16_t>(slot_id);
  dev.status = pooled;
  dev.link_status = 0x3;
  dev.fpga_temp = 50;
  s.mpdevs.push_back(dev);
  if (pooled) {
    s.pool.mpdev_count++;
  } else {
    s.pool.unpooled_mpdev_count++;
  }
  s.pool.size_gb += pooled ? size_gb : 0;
  return s.mpdevs.back();
}

mpctl_mpn& add_mpn(uint32_t size_gb, uint16_t slot_id, int location) {
  State& s = state();
  mpctl_mpn mpn{};
  mpn.id = static_cast<unsigned int>(s.mpns.size());
  mpn.region_id = mpn.id;
  mpn.status = 0;
  mpn.mode = MPCTL_MPN_MODE_PMEM;
  mpn.namespace_numa = -1;
  mpn.size = static_cast<unsigned long long>(size_gb) << 30;
  mpn.size_gb = size_gb;
  mpn.host_phys_addr = 0x1000000000ULL + (static_cast<uint64_t>(mpn.id) << 36);
  mpn.location = location;
  mpn.slot_id = slot_id;
  s.mpns.push_back(mpn);
  s.pool.mpn_count++;
  return s.mpns.back();
}

}  // namespace mock_mpctl

using mock_mpctl::state;

int mpctl_init(struct mpctl_ctx** mctx) {
  state().init_calls++;
  if (state().init_rc != MPCTL_RC_SUCCESS) {
    return state().init_rc;
  }
  *mctx = new mpctl_ctx{};
  state().open_contexts++;
  return MPCTL_RC_SUCCESS;
}

void mpctl_close(struct mpctl_ctx* mctx) {
  state().close_calls++;
  state().open_contexts--;
  delete mctx;
}

int mpctl_host_init_discovery(struct mpctl_ctx*) {
  state().host_init_calls++;
  return state().op_rc;
}

int mpctl_pool_create(struct mpctl_ctx*) {
  state().pool_create_calls++;
  if (state().op_rc == MPCTL_RC_SUCCESS) {
    state().pool.ready = 1;
  }
  return state().op_rc;
}

int mpctl_pool_add(struct mpctl_ctx*, unsigned int mpn_id) {
  state().pool_add_calls++;
  state().last_pool_add_id = mpn_id;
  return state().op_rc;
}

int mpctl_mpn_online(struct mpctl_ctx*, unsigned int mpn_id) {
  state().online_calls++;
  if (mpn_id >= state().mpns.size()) {
    return MPCTL_RC_MPN_NOT_FOUND;
  }
  if (state().op_rc == MPCTL_RC_SUCCESS) {
    mpctl_mpn& mpn = state().mpns[mpn_id];
    mpn.status = 1;
    mpn.mode = MPCTL_MPN_MODE_NUMA;
    mpn.namespace_numa = state().online_numa_node;
  }
  return state().op_rc;
}

int mpctl_mpn_offline(struct mpctl_ctx*, unsigned int mpn_id) {
  state().offline_calls++;
  if (mpn_id >= state().mpns.size()) {
    return MPCTL_RC_MPN_NOT_FOUND;
  }
  if (state().op_rc == MPCTL_RC_SUCCESS) {
    mpctl_mpn& mpn = state().mpns[mpn_id];
    mpn.status = 0;
    mpn.mode = MPCTL_MPN_MODE_PMEM;
    mpn.namespace_numa = -1;
    mpn.dax_devname[0] = '\0';
  }
  return state().op_rc;
}

int mpctl_mpn_enable_dax(struct mpctl_ctx*, unsigned int mpn_id) {
  state().enable_dax_calls++;
  if (mpn_id >= state().mpns.size()) {
    return MPCTL_RC_MPN_NOT_FOUND;
  }
  if (state().op_rc == MPCTL_RC_SUCCESS) {
    mpctl_mpn& mpn = state().mpns[mpn_id];
    mpn.status = 1;
    mpn.mode = MPCTL_MPN_MODE_DEVDAX;
    snprintf(mpn.dax_devname, sizeof(mpn.dax_devname), "dax%u.0", mpn_id);
  }
  return state().op_rc;
}

struct mpctl_pool* mpctl_pool_get_info(struct mpctl_ctx*) {
  return state().fail_get_info ? nullptr : &state().pool;
}

struct mpctl_mpn* mpctl_mpn_get_info(struct mpctl_ctx*, unsigned int mpn_id) {
  if (state().fail_get_info || mpn_id >= state().mpns.size()) {
    return nullptr;
  }
  return &state().mpns[mpn_id];
}

struct mpctl_mpdev* mpctl_mpdev_get_info(struct mpctl_ctx*,
                                         unsigned int mpdev_id) {
  if (state().fail_get_info || mpdev_id >= state().mpdevs.size()) {
    return nullptr;
  }
  return &state().mpdevs[mpdev_id];
}
