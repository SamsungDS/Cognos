cmake_minimum_required(VERSION 3.7) 

include(FindPackageHandleStandardArgs)
project(svk_ras_einj_demo) # Project name

link_directories(${CMAKE_SOURCE_DIR}/build/adapters/mock_adapter)
add_executable(svk_ras_einj_demo ras_err_inject_demo.cpp)

target_link_libraries(svk_ras_einj_demo numa mock) # Link library to target
