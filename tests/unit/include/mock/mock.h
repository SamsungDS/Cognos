#ifndef _MOCK__H_
#define _MOCK__H_

/**
 * @def DEFINE_RETURN_MOCK
 * @brief Defines a mock function for unit testing with a return value.
 */
#define DEFINE_RETURN_MOCK(fn, ret) \
  bool ut_##fn##_mocked = false;    \
  ret ut_##fn

#endif  // _MOCK__H_