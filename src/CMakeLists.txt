# Collect source files
file(GLOB SOURCES *.cc tm/*.cc)
file(GLOB HEADERS include/*.h tm/include/*.h)

# Create a library
add_library(svkcxl ${SOURCES} ${HEADERS})
add_subdirectory(cmmh)
set(SVKCXL_INCLUDE_DEST "include/")

find_library(JSON NAMES "libjansson.so" REQUIRED)
if (NOT JSON)
  message(FATAL_ERROR "libjansson not found, install libjansson-dev for ubuntu, jansson-devel for fedora if you need to build libcxl back-end")
else()
  message(STATUS "found libjansson for libcxl")
endif()

target_include_directories(svkcxl PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include/" "${CMAKE_CURRENT_SOURCE_DIR}/tm/include/" ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS} ${FMAPI_INCLUDE_PATH})
target_link_directories(svkcxl PRIVATE "${FMAPI_INCLUDE_PATH}/build" ${SVKMGMTFW_LIB_DIRS} ${SVKFRAMEWORK_LIBRARY_DIRS})
target_link_libraries(svkcxl mbox_a1_shared svcmgr jansson zmq numa svklogger yaml-cpp)

add_definitions("-DBOOST_ALLOW_DEPRECATED_HEADERS")
add_definitions("-DBOOST_BIND_GLOBAL_PLACEHOLDERS")

if(BUILD_TESTING)
  add_definitions(-DTEST_BUILD=1 )
else()
  add_definitions(-DTEST_BUILD=0 )
endif()
install(FILES ${HEADERS} DESTINATION ${SVKCXL_INCLUDE_DEST})
install(
    TARGETS svkcxl
    EXPORT cxlTargets
    # name of the CMake "export group" containing the targets we want to install
    LIBRARY DESTINATION ${SVKCXL_LIB_DEST}
    INCLUDES DESTINATION "${SVKCXL_INCLUDE_DEST}"
)

