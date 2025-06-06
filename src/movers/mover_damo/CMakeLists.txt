# Collect source files
file(GLOB SOURCES *.cc)
file(GLOB HEADERS *.h)

# Create a library
add_library(mover_damo SHARED ${SOURCES} ${HEADERS})

target_include_directories(mover_damo PUBLIC "${SVKME_SRC_INCLUDE}")
target_link_libraries(mover_damo numa yaml-cpp)

add_definitions("-DBOOST_ALLOW_DEPRECATED_HEADERS")
add_definitions("-DBOOST_BIND_GLOBAL_PLACEHOLDERS")

if(BUILD_TESTING)
  add_definitions(-DTEST_BUILD=1 )
else()
  add_definitions(-DTEST_BUILD=0 )
endif()

install(
    TARGETS mover_damo
    LIBRARY DESTINATION "${CMAKE_INSTALL_PREFIX}/logic_modules/movers/${SVKME_LIB_DEST}"
)

install(
    FILES "config/damo_config.json"
    DESTINATION "${CMAKE_INSTALL_PREFIX}/config/"
)

install(
    FILES "tools/tm_gen_config.py"
    DESTINATION "${CMAKE_INSTALL_PREFIX}/config/"
)

