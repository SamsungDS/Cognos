# Collect source files
file(GLOB SOURCES *.cc)
file(GLOB HEADERS *.h)

# Create a library
add_library(numa_move_all SHARED ${SOURCES} ${HEADERS})

target_include_directories(numa_move_all PUBLIC "${SVKME_SRC_INCLUDE}")
target_link_libraries(numa_move_all numa)

add_definitions("-DBOOST_ALLOW_DEPRECATED_HEADERS")
add_definitions("-DBOOST_BIND_GLOBAL_PLACEHOLDERS")
install(
    TARGETS numa_move_all
    LIBRARY DESTINATION "${CMAKE_INSTALL_LIBDIR}/movers/"
)

