#ifndef _MOCK__H_
#define _MOCK__H_

extern "C" {

#define DEFINE_RETURN_MOCK(fn, ret) \
  bool ut_##fn##_mocked = false;    \
  ret ut_##fn

/*
 * For controlling mocked function behavior, setting
 * and getting values from the stub, the _P macros are
 * for mocking functions that return pointer values.
 */
#define MOCK_SET(fn, val)  \
  ut_##fn##_mocked = true; \
  ut_##fn = val

#define MOCK_GET(fn) ut_##fn

#define MOCK_CLEAR(fn) ut_##fn##_mocked = false

#define MOCK_CLEAR_P(fn)    \
  ut_##fn##_mocked = false; \
  ut_##fn = NULL

/* for declaring function protoypes for wrappers */
#define DECLARE_WRAPPER(fn, ret, args) \
  extern bool ut_##fn##_mocked;        \
  extern ret ut_##fn;                  \
  ret __wrap_##fn args;                \
  ret __real_##fn args

/*
 * For defining the implementation of wrappers for syscalls.
 * Avoid nested macro calls to prevent macro expansion of fn.
 */
#define DEFINE_WRAPPER(fn, ret, dargs, pargs)   \
  bool ut_##fn##_mocked = false;                \
  ret ut_##fn;                                  \
  __attribute__((used)) ret __wrap_##fn dargs { \
    if (!ut_##fn##_mocked) {                    \
      return __real_##fn pargs;                 \
    } else {                                    \
      return ut_##fn;                           \
    }                                           \
  }

/* DEFINE_STUB is for defining the implementation of stubs for SPDK funcs. */
#define DEFINE_STUB(fn, ret, dargs, val) \
  bool ut_##fn##_mocked = true;          \
  ret ut_##fn = val;                     \
  ret fn dargs;                          \
  ret fn dargs { return MOCK_GET(fn); }

/* DEFINE_STUB_V macro is for stubs that don't have a return value */
#define DEFINE_STUB_V(fn, dargs) \
  void fn dargs;                 \
  void fn dargs {}

#define HANDLE_RETURN_MOCK(fn) \
  if (ut_##fn##_mocked) {      \
    return ut_##fn;            \
  }

/* declare wrapper protos (alphabetically please) here */
DECLARE_WRAPPER(calloc, void *, (size_t nmemb, size_t size));
}
#endif  // _MOCK__H_