# Collect source files
file(GLOB SOURCES *.cc)
file(GLOB HEADERS *.h)

# Create a library
add_library(cme_mover_dummy SHARED ${SOURCES} ${HEADERS})
target_include_directories(cme_mover_dummy PUBLIC "${SVKME_SRC_INCLUDE}")
install(
    TARGETS cme_mover_dummy
    LIBRARY DESTINATION "${CMAKE_INSTALL_LIBDIR}/movers/"
)

