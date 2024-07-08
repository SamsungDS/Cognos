# Collect source files
file(GLOB SOURCES *.cc)

# Create a library
add_library(cxl_lib ${SOURCES})

target_include_directories(cxl_lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

target_link_directories(cxl_lib PRIVATE "${CMAKE_INCLUDE_PATH}/build")

#add an executable target linked with library
target_link_libraries(cxl_lib mbox_a1_shared jansson)

