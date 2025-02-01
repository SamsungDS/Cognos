# Collect source files
file(GLOB SOURCES *.cc)
file(GLOB HEADERS include/*.h)

# Create a library
add_library(cme ${SOURCES} ${HEADERS})

find_library(JSON NAMES "libjansson.so" REQUIRED)
if (NOT JSON)
  message(FATAL_ERROR "libjansson not found, install libjansson-dev for ubuntu, jansson-devel for fedora if you need to build libcxl back-end")
else()
  message(STATUS "found libjansson for libcme")
endif()

target_include_directories(cme PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include/" ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS})
target_link_directories(cme PRIVATE ${SVKMGMTFW_LIB_DIRS} ${SVKFRAMEWORK_LIBRARY_DIRS})
target_link_libraries(cme jansson numa svklogger yaml-cpp)

add_definitions("-DBOOST_ALLOW_DEPRECATED_HEADERS")
add_definitions("-DBOOST_BIND_GLOBAL_PLACEHOLDERS")

if(BUILD_TESTING)
  add_definitions(-DTEST_BUILD=1 )
else()
  add_definitions(-DTEST_BUILD=0 )
endif()
install(FILES ${HEADERS} DESTINATION ${SVKCME_INCLUDE_DEST})
install(
    TARGETS cme
    EXPORT cmeTargets
    # name of the CMake "export group" containing the targets we want to install
    LIBRARY DESTINATION ${SVKCME_LIB_DEST}
    INCLUDES DESTINATION "${SVKCME_INCLUDE_DEST}"
)
