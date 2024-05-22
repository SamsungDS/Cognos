#ifndef __CXL_PLUGIN_SC_ID_H__
#define __CXL_PLUGIN_SC_ID_H__

#include "types.h"

/**
 * @brief simple class sc_id
 * @details This class encapsulates unsigned 64 bit int ID
 *          and provides modifiers & accessors for ID.
 */
class sc_id {
 public:
  sc_id() : sc_id(0){};

  /**
   * @brief sc_id constructor with one parameter.
   * @details This constructor takes any value of type uint64_t as parameter.
   * @param id any value of type uint64_t.
   */
  explicit sc_id(uint64_t const& id) : s_id(id) {}

  ~sc_id() = default;

  /**
   * @brief mutator of id variable.
   * @param id set id value to data member.
   */
  void set_sc_id(uint64_t const& id) { s_id = id; }

  /**
   * @brief accessor of id variable.
   * @details get id value.
   */
  uint64_t get_sc_id() const { return s_id; }

  /**< Equality operator for key comparison in collision case*/
  bool operator==(const sc_id& other) const { return s_id == other.s_id; }

 public:
  /**< id value */
  uint64_t s_id{1};
};

/**
 * @brief custom hash function.
 * @details If two class has same hash value. Then there is a collision.
 *          for that case ==operator overlaoding defines custom class.
 */
class hash_sc_id {
 public:
  size_t operator()(const sc_id& key) const { return key.s_id; }
};

#endif
