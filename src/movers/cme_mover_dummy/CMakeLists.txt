# Collect source files
file(GLOB SOURCES *.cc)
file(GLOB HEADERS *.h)

# Create a library
add_library(cme_mover_dummy SHARED ${SOURCES} ${HEADERS})
target_include_directories(cme_mover_dummy PUBLIC "${SVKME_SRC_INCLUDE}")

if(BUILD_TESTING)
  add_definitions(-DTEST_BUILD=1 )
else()
  add_definitions(-DTEST_BUILD=0 )
endif()

install(
    TARGETS cme_mover_dummy
    LIBRARY DESTINATION "${CMAKE_INSTALL_PREFIX}/logic_modules/movers/${SVKME_LIB_DEST}"
)

