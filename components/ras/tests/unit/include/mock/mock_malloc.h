
#include <cstddef>

#include "mock.h"

extern "C" {
DEFINE_WRAPPER(calloc, void *, (size_t nmemb, size_t size), (nmemb, size))
}
