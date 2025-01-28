#ifndef FABRIC_MANAGER_H
#define FABRIC_MANAGER_H
#include <jansson.h>

#include <vector>

#include "sc_host.h"
#include "sc_id.h"
#include "sc_sld.h"

class FabricManager {
 public:
  /**
   * @brief Constructor with a direct config object reference.
   */
  explicit FabricManager(json_t* config);

  virtual ~FabricManager();

  /**
   * @brief Returns a topology hierarchy for cluster configuration.
   * @param buffer to hold json data.
   * @return setup info as JSON.
   */
  virtual size_t setup_info(std::string& buffer);

  void set_fm_type(std::string id_type);

  std::string get_fm_type() const;

  sc_id get_fmid() const;

  uint64_t hash_id_json(json_t* id_json, const std::string& fm_type);

  void cleanup();

 private:
  std::vector<sc_host> hosts;
  std::vector<sc_device> devs;
  // fabric manager id
  sc_id id;
  std::string fm_type;

  /**
   * @brief Helper to parse the direct attached host config.
   */
  void parse_config(json_t* config);
};
#endif
