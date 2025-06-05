
#include <cstddef>

#include "mock.h"

extern "C" {
DEFINE_WRAPPER(malloc, void *, (size_t size), (size))
}
