cmake_minimum_required(VERSION 3.7) 

include(FindPackageHandleStandardArgs)
project(svk_ras_einj) # Project name

find_program(MAKE_EXECUTABLE NAMES make gmake REQUIRED)
include (ExternalProject)
set(MCE_INJECT_DIR ${CMAKE_BINARY_DIR}/mce-inject)
set(MCE_INJECT_EXECUTABLE mce-inject)
ExternalProject_Add(mce-inject
    GIT_REPOSITORY https://github.com/andikleen/mce-inject.git
    SOURCE_DIR        "${CMAKE_BINARY_DIR}/mce-inject"
    CONFIGURE_COMMAND ""
    BUILD_COMMAND ${MAKE_EXECUTABLE} -j${Ncpu} -C ${MCE_INJECT_DIR}
    INSTALL_COMMAND ""
)

install(FILES ${MCE_INJECT_DIR}/${MCE_INJECT_EXECUTABLE} DESTINATION "adapters/mock/tools" PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)

add_executable(svk_ras_einj main.cpp)

find_path(rapidjson_INCLUDE_DIR NAMES "rapidjson/document.h")
if(NOT rapidjson_INCLUDE_DIR)
    message(FATAL_ERROR "error: Cannot find rapidjson include directory")
endif()

find_package_handle_standard_args( rapidjson REQUIRED_VARS rapidjson_INCLUDE_DIR)

target_link_libraries(svk_ras_einj numa) # Link library to target

configure_file(${CMAKE_CURRENT_SOURCE_DIR}/config.json ${CMAKE_CURRENT_BINARY_DIR}/config.json @ONLY)

install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/config.json DESTINATION "adapters/mock/tools" )
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/svk_ras_einj DESTINATION "adapters/mock/tools" PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)

