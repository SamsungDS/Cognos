# Collect source files
file(GLOB SOURCES *.cc)

# Create a library
add_library(cxl_lib ${SOURCES})

target_include_directories(cxl_lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

