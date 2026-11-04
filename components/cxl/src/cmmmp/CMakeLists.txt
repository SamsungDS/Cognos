# Set the plugin name
set(PLUGIN_NAME cmmmp)

if(NOT WITH_CMMMP)
  message(STATUS "CMM-MP plugin disabled (WITH_CMMMP=OFF)")
  return()
endif()

if(NOT EXISTS ${CMMMP_STATIC_LIB})
  message(FATAL_ERROR "libmpctl.a not found at ${CMMMP_STATIC_LIB}")
endif()

# libmpctl uses libcxl / libndctl / libdaxctl from the ndctl project
find_library(CXL_LIB NAMES cxl)
find_library(NDCTL_LIB NAMES ndctl)
find_library(DAXCTL_LIB NAMES daxctl)
if(NOT CXL_LIB OR NOT NDCTL_LIB OR NOT DAXCTL_LIB)
  message(WARNING "libcxl / libndctl / libdaxctl not found, skipping CMM-MP plugin. "
                  "Install libcxl-dev libndctl-dev libdaxctl-dev for ubuntu, "
                  "cxl-devel ndctl-devel daxctl-devel for rocky / ol.")
  return()
endif()

# libmpctl.a is a prebuilt C++ library (GCC 13, glibc >= 2.38). Only build the
# plugin where it actually links with the local toolchain and C library.
include(CheckCXXSourceCompiles)
set(CMAKE_REQUIRED_INCLUDES ${CMMMP_THIRD_PARTY_DIR})
set(CMAKE_REQUIRED_LIBRARIES ${CMMMP_STATIC_LIB} ${CXL_LIB} ${NDCTL_LIB} ${DAXCTL_LIB})
check_cxx_source_compiles("
#include \"libmpctl.h\"
int main() {
  struct mpctl_ctx* ctx = nullptr;
  return mpctl_init(&ctx);
}" CMMMP_LIBMPCTL_LINKS)
unset(CMAKE_REQUIRED_INCLUDES)
unset(CMAKE_REQUIRED_LIBRARIES)
if(NOT CMMMP_LIBMPCTL_LINKS)
  message(WARNING "${CMMMP_STATIC_LIB} does not link on this platform "
                  "(requires glibc >= 2.38), skipping CMM-MP plugin")
  return()
endif()

file(GLOB CMMMP_SOURCES "*.cc")
file(GLOB CMMMP_HEADERS "include/*.h")

add_library(${PLUGIN_NAME} SHARED ${CMMMP_SOURCES} ${CMMMP_HEADERS})
add_dependencies(${PLUGIN_NAME} svkcxl)

target_include_directories(${PLUGIN_NAME} PRIVATE
"${CMAKE_CURRENT_SOURCE_DIR}/include"
"${PROJECT_SOURCE_DIR}/src/include"
${CMMH_THIRD_PARTY_DIR}
${CMMMP_THIRD_PARTY_DIR}
${SVKMGMTFW_INCLUDE_DIRS}
${SVKFRAMEWORK_INCLUDE_DIRS}
)

target_link_directories(${PLUGIN_NAME} PRIVATE
${SVKMGMTFW_LIB_DIRS}
${SVKFRAMEWORK_LIBRARY_DIRS}
)

# keep libmpctl symbols private to the plugin
target_link_options(${PLUGIN_NAME} PRIVATE "-Wl,--exclude-libs,libmpctl.a")

# Link required system and framework libraries
target_link_libraries(${PLUGIN_NAME}
 PRIVATE
 ${CMMMP_STATIC_LIB}
 ${CXL_LIB}
 ${NDCTL_LIB}
 ${DAXCTL_LIB}
 jansson
 numa
 svklogger
 ${PROJECT_BINARY_DIR}/src/libsvkcxl.so
)

install(TARGETS ${PLUGIN_NAME}
LIBRARY DESTINATION "${CMMMP_LIB_PATH}")
