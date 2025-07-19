cmake_minimum_required(VERSION 3.7) 

include(FindPackageHandleStandardArgs)
project(svk_ras_einj_monitor) # Project name

link_directories(${CMAKE_SOURCE_DIR}/build/adapters/mock_adapter)
add_executable(svk_ras_einj_monitor ras_err_inject_demo.cpp)

target_link_libraries(svk_ras_einj_monitor numa mock) # Link library to target

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/svk_ras_einj_monitor DESTINATION "adapters/mock/tools" PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)
