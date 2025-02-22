cmake_minimum_required(VERSION 3.7) 

include(FindPackageHandleStandardArgs)
project(mslras) # Project name

add_executable(mslras main.cpp config.json) 

find_path(rapidjson_INCLUDE_DIR NAMES "rapidjson/document.h")
if(NOT rapidjson_INCLUDE_DIR)
    message(FATAL_ERROR "error: Cannot find rapidjson include directory")
endif()

find_package_handle_standard_args( rapidjson REQUIRED_VARS rapidjson_INCLUDE_DIR)

target_link_libraries(mslras numa) # Link library to target

install(FILES config.json DESTINATION ${CMAKE_BINARY_DIR} )
