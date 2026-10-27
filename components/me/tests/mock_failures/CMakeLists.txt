# Collect source files
file(GLOB SOURCES *.cc)
file(GLOB HEADERS *.h)

# Create a library
add_library(register_mover SHARED ${SOURCES} ${HEADERS})
target_include_directories(register_mover PUBLIC "${CMAKE_SOURCE_DIR}/src/include" ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS})

install(
    TARGETS register_mover
)

