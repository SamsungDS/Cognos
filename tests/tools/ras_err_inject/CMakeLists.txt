cmake_minimum_required(VERSION 3.7) 

include(FindPackageHandleStandardArgs)
project(mslras) # Project name

add_executable(mslras main.cpp config.json) 

find_path(nlohmann_INCLUDE_DIR NAMES "nlohmann/json.hpp")
if(NOT nlohmann_INCLUDE_DIR)
    message(FATAL_ERROR "error: Cannot find nlohmann/json.hpp")
endif()

find_package_handle_standard_args( nlohmann REQUIRED_VARS nlohmann_INCLUDE_DIR)

target_link_libraries(mslras numa) # Link library to target

install(FILES config.json DESTINATION ${CMAKE_BINARY_DIR} )
