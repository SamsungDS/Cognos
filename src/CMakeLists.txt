# Collect source files
file(GLOB SOURCES *.cc)
file(GLOB HEADERS include/*.h)

# Create a library
add_library(svkme ${SOURCES} ${HEADERS})

#add_library(my_shared_lib SHARED samples/movers/cme_mover_1.cc)

find_library(JSON NAMES "libjansson.so" REQUIRED)
if (NOT JSON)
  message(FATAL_ERROR "libjansson not found, install libjansson-dev for ubuntu, jansson-devel for fedora if you need to build libcxl back-end")
else()
  message(STATUS "found libjansson for libcme")
endif()

target_include_directories(svkme PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include/" ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS})
target_link_directories(svkme PRIVATE ${SVKMGMTFW_LIB_DIRS} ${SVKFRAMEWORK_LIBRARY_DIRS})
target_link_libraries(svkme jansson svklogger)

add_definitions("-DBOOST_ALLOW_DEPRECATED_HEADERS")
add_definitions("-DBOOST_BIND_GLOBAL_PLACEHOLDERS")

set(SVKME_SRC_INCLUDE "${CMAKE_CURRENT_SOURCE_DIR}/include/")
set(SVKME_SRC_PATH "${CMAKE_CURRENT_SOURCE_DIR}/")
add_subdirectory("profilers")
add_subdirectory("movers")


if(BUILD_TESTING)
  add_definitions(-DTEST_BUILD=1 )
else()
  add_definitions(-DTEST_BUILD=0 )
endif()
install(FILES ${HEADERS} DESTINATION ${SVKME_INCLUDE_DEST})
install(
    TARGETS svkme
    EXPORT svkmeTargets
    # name of the CMake "export group" containing the targets we want to install
    LIBRARY DESTINATION ${SVKME_LIB_DEST}
)
