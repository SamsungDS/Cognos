# Collect source files
file(GLOB SOURCES *.cc "${SVKME_SRC_PATH}/cme_utils.cc")
file(GLOB HEADERS *.h)

# Create a library
add_library(numa_move_all SHARED ${SOURCES} ${HEADERS})

target_include_directories(numa_move_all PUBLIC "${SVKME_SRC_INCLUDE}" ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS})
target_link_directories(numa_move_all PUBLIC  ${SVKMGMTFW_LIB_DIRS} ${SVKFRAMEWORK_LIBRARY_DIRS})
target_link_libraries(numa_move_all numa svkframework svkme nlohmann_json)

add_definitions("-DBOOST_ALLOW_DEPRECATED_HEADERS")
add_definitions("-DBOOST_BIND_GLOBAL_PLACEHOLDERS")

if(BUILD_TESTING)
  add_definitions(-DTEST_BUILD=1 )
else()
  add_definitions(-DTEST_BUILD=0 )
endif()

install(
    TARGETS numa_move_all
    LIBRARY DESTINATION "${CMAKE_INSTALL_PREFIX}/logic_modules/movers/${SVKME_LIB_DEST}"
)

