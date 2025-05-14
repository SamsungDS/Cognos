#ifndef __CXL_PLUGIN_MBOX_H__
#define __CXL_PLUGIN_MBOX_H__

#include <cstdint>
#include "mbox_a1.h"
#include "sc_device.h"
#include "sc_mld.h"
#include "sc_sld.h"

class sc_mbox : public sc_device {
 public:
  sc_mbox();

  /**
   * @brief parameterized MBOX constructor.
   * @details This constructor passes mb_switch to sc_switch class, mb_fm_id to
   * sc_id class, mb_id to sc_device class along with some literals.
   */
  sc_mbox(uint64_t mb_id, uint64_t mb_fm_id, sc_switch mb_switch);

  ~sc_mbox();

  /* get sc_id class object */
  sc_id d_get_id() const override;

  /**
   * @brief delete memory box - sld device.
   * @details This method takes sc_id and deletes the matched sld device if
   * exists.
   */
  // int mbox_delete_sld(sc_id d_id, uint32_t d_port);
  int mbox_delete_sld(sc_sld sld);

  /**
   * @brief delete memory box - mld device.
   * @details This method takes sc_id and deletes the matched mld device if
   * exists.
   */
  int mbox_delete_mld(sc_mld mld);

  /**
   * @brief get memory box switch information.
   * @details return switch info.
   */
  std::string mbox_get_switch_info();

  /**
   * @brief list slds
   */
  std::list<sc_sld> mbox_list_connected_slds();

  /**
   * @brief list mlds
   */
  std::list<sc_mld> mbox_list_connected_mlds();

  /**
   * @brief list slds
   */
  std::list<sc_host> mbox_list_connected_hosts();

  /**
   * @brief create sld as per the capacity
   * @param capacity required capacity
   */
  sc_sld mbox_create_sld(uint64_t capacity);

  /**
   * @brief create mld as per the capacity
   * @param capacity required capacity
   */
  sc_mld mbox_create_mld(uint64_t capacity);

  /**
   * @brief verify if device port is part of the host endpoint.
   * @param d_id device id
   */
  int fetch_device_port(uint64_t d_id);

  int delete_d_ids(sc_device dev);

  int delete_pdev(sc_device dev);

  /**
   * @brief attach device to host.
   * @param d_id upstream host id.
   * @param h_id downstream device id.
   * @param mode direct or shared.
   */
  int d_attach(uint64_t d_id, uint64_t h_id, std::string mode);

  /**
   * @brief detach device to host.
   * @param d_id upstream host id.
   * @param h_id downstream device id.
   * @param mode direct or shared.
   */
  int d_detach(uint64_t d_id, uint64_t h_id, std::string mode);

  /**
   * @brief add sld object to map.
   */
  void addSld(sc_sld& sld);

  /**
   * @brief add mld object to map.
   */
  void addMld(sc_mld& mld);

  /**
   * @brief add host object to map.
   */
  void addHost(sc_host& host);

  /**< get mbox_connected_slds*/
  std::unordered_map<sc_id, sc_sld, hash_sc_id> get_slds_map() const;

  /**< get mbox_connected_mlds*/
  std::unordered_map<sc_id, sc_mld, hash_sc_id> get_mlds_map() const;

  /**< get mbox_connected_hosts*/
  std::unordered_map<sc_id, sc_host, hash_sc_id> get_hosts_map() const;

  std::unordered_map<uint64_t, sc_id> get_d_ids() const;
  std::unordered_map<uint32_t, sc_id> get_pdev() const;
  std::unordered_map<uint32_t, std::list<sc_id>>& get_phost();

 private:
  /**< memory box fabric manager */
  sc_id mbox_fm_id;

  /**< memory box switch information*/
  sc_switch mbox_switch;

  /**< umap with key as custom class sc_id and value as custom class sc_sld */
  std::unordered_map<sc_id, sc_sld, hash_sc_id> mbox_connected_slds;

  /**< umap with key as custom class sc_id and value as custom class sc_mld */
  std::unordered_map<sc_id, sc_mld, hash_sc_id> mbox_connected_mlds;

  /**< map with key as custom class sc_id and value as custom class sc_host */
  std::unordered_map<sc_id, sc_host, hash_sc_id> mbox_connected_hosts;

  /**< scalar type dev_id -> object type dev_id (sc_id class) */
  std::unordered_map<uint64_t, sc_id> d_ids;
  /**< scalar type host_id -> object type host_id (sc_id class) */
  std::unordered_map<uint64_t, sc_id> h_ids;

  /**< device port -> device object */
  std::unordered_map<uint32_t, sc_id> pdev;

  /**< host target port -> list of host object */
  std::unordered_map<uint32_t, std::list<sc_id>> phost;
};

#endif
