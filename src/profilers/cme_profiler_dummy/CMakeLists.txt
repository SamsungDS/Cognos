# Collect source files
file(GLOB SOURCES *.cc)
file(GLOB HEADERS *.h)

# Create a library
add_library(cme_profiler_dummy SHARED ${SOURCES} ${HEADERS})
target_include_directories(cme_profiler_dummy PUBLIC "${SVKME_SRC_INCLUDE}")
install(
    TARGETS cme_profiler_dummy
    LIBRARY DESTINATION "${CMAKE_INSTALL_PREFIX}/logic_modules/profilers/${SVKME_LIB_DEST}"
)

