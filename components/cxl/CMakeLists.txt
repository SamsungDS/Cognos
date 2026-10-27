cmake_minimum_required(VERSION 3.7)

find_package(PkgConfig REQUIRED)
pkg_check_modules(SVKFRAMEWORK REQUIRED svkframework)

include(${CMAKE_SOURCE_DIR}/cmake/svk_global.cmake)

#Set this project's name.
set(SVK_CXL_VERSION ${GIT_REPO_VERSION})
set(SVKCXL "svkcxl")
project(${SVKCXL} VERSION ${SVK_CXL_VERSION}
	DESCRIPTION "SVK CXL")

include(GNUInstallDirs)

#Centralized install paths
set(SVK_BASE_PATH "/usr/local/svk/feature_modules/cxl")
set(SVK_CONFIG_PATH "${SVK_BASE_PATH}/config")
set(SVK_LIB_PATH "${SVK_BASE_PATH}/lib64")
set(SVK_LOGIC_MODULE_PATH "${SVK_BASE_PATH}/logic_modules")

#Subpath for logic modules
set(CMMH_LIB_PATH "${SVK_LOGIC_MODULE_PATH}/cmmh/lib64")

#Third party lib paths
if (CMAKE_SYSTEM_NAME STREQUAL "Linux")
  message(STATUS "-----------BUILD ON LINUX -----------------")
#Check for distribution ID
  execute_process(COMMAND cat /etc/os-release COMMAND grep -e "^ID=" COMMAND awk -F= "{ print $2 }" COMMAND sed "s/\"//g" OUTPUT_VARIABLE os_distro OUTPUT_STRIP_TRAILING_WHITESPACE)
  message (STATUS "DISTRO FOUND ${os_distro}")
#Check for Ubuntu / Oracle Linux / Rocky specific ID
  if ("${os_distro}" STREQUAL "ubuntu")
    set(CMMH_THIRD_PARTY_DIR "${PROJECT_SOURCE_DIR}/third_party/" CACHE STRING "Path to third party directory")
    set(CMMH_STATIC_LIB "${PROJECT_SOURCE_DIR}/third_party/libcmmh.a" CACHE STRING "static lib path to cmmh")
  elseif ("${os_distro}" MATCHES "^(ol|rocky)$")
    set(CMMH_THIRD_PARTY_DIR "${PROJECT_SOURCE_DIR}/third_party/OL" CACHE STRING "Path to third party directory")
    set(CMMH_STATIC_LIB "${PROJECT_SOURCE_DIR}/third_party/OL/libcmmh.a" CACHE STRING "static lib path to cmmh")
  else()
    message(FATAL_ERROR "Unsupported Linux distribution: ${os_distro}")
  endif()

endif()

#For header / library install destinations
set(SVKCXL_INCLUDE_DEST "include")
set(SVKCXL_LIB_DEST "${SVK_LIB_PATH}")

option(BUILD_SHARED_LIBS "Generate shared libs" ON)

set(PKG_CONFIG_INCLUDEDIR "\${prefix}/${CMAKE_INSTALL_INCLUDEDIR}")
set(PKG_CONFIG_LIBDIR "\${exec_prefix}/${CMAKE_INSTALL_LIBDIR}")
set(pkg_config "${CMAKE_BINARY_DIR}/${SVKCXL}.pc")
set(pkgconfig_install_dir "${CMAKE_INSTALL_LIBDIR}/pkgconfig")
set(SVKCXL_LIB_DEST "lib64/")
set(SVKCXL_INCLUDE_DEST "include/")
set(SVKMGMTFW_DIRS "/usr/local/svk/mgmt-fw")
set(SVKMGMTFW_INCLUDE_DIRS "/usr/local/svk/mgmt-fw/include")
set(SVKMGMTFW_LIB_DIRS "/usr/local/svk/mgmt-fw/lib64")
set(SVKCXL_FMAPI_DIRS "/usr/local/lib/cxl_memory_box")
configure_file("cmake/${SVKCXL}.pc.in" "${pkg_config}" @ONLY)

find_package(PkgConfig REQUIRED)
pkg_check_modules(SVKFRAMEWORK REQUIRED svkframework)

#Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -rdynamic")

#Include custom cmake modules
list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake")

#Set coverage flags for GCC / Clang
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    if(WITH_COVERAGE)
        message(STATUS "Building with coverage")
        set(COVERAGE_FLAGS "--coverage -fprofile-arcs -ftest-coverage")
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${COVERAGE_FLAGS}")
        set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} ${COVERAGE_FLAGS}")
    endif()
endif()

#Add subdirectories
add_subdirectory(src)
if(BUILD_TESTING)
    add_subdirectory(tests)
endif()

add_subdirectory(utils)

include(CMakePackageConfigHelpers)
write_basic_package_version_file(
        SVKCXLConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY AnyNewerVersion
    )

    set(SVKCXL_CMAKE_DEST "cmake/")

install(
    FILES
        "cmake/svkcxl-config.cmake"
        "${CMAKE_CURRENT_BINARY_DIR}/SVKCXLConfigVersion.cmake"
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/${SVKCXL_CMAKE_DEST}
    )
install(CODE "
    file(WRITE \"svk-cxl-x86_64.conf\" \"\\n${CMAKE_INSTALL_PREFIX}/lib\\n\")
    file(APPEND \"svk-cxl-x86_64.conf\" \"\\n${CMAKE_INSTALL_PREFIX}/lib64\\n\")
")

if(WITH_FMAPI)
    install(
        FILES "${FMAPI_LIBRARY_PATH}"
        DESTINATION "${SVKCXL_FMAPI_DIRS}"
    )
    install(CODE "
        file(APPEND \"svk-cxl-x86_64.conf\" \"\\n${SVKCXL_FMAPI_DIRS}\\n\")
    ")
    if(MOCK_FLAG)
        install(
            FILES "${FMAPI_INCLUDE_PATH}/sample_json/input.json"
            DESTINATION "${SVKMGMTFW_DIRS}"
        )
    endif()
endif()

install(
    FILES "build/svk-cxl-x86_64.conf"
    DESTINATION "/etc/ld.so.conf.d"
)

install(
    FILES "config/zmq_config.json"
    DESTINATION "/etc/svk/"
)

install(
    FILES "config/damo_config.json"
    DESTINATION "/etc/svk/"
)

install(
    FILES "tools/tm_gen_config.py"
    DESTINATION "/etc/svk/"
)

install(
    FILES "scripts/dependencies/python/requirements_deploy.txt"
    DESTINATION "scripts/dependencies/python"
)

install(
    FILES "${pkg_config}"
    DESTINATION "${pkgconfig_install_dir}"
)

install(FILES 
	config/cxl.conf 
	config/log.conf 
	config/cxl_dev_id_map.json 
	"${PROJECT_SOURCE_DIR}/tests/input.json"
	src/cxl_utils.py
DESTINATION "${SVK_CONFIG_PATH}")

#Check for Ubuntu / Oracle Linux / Rocky specific ID
install(FILES ${CMMH_THIRD_PARTY_DIR}/libcmmh.h
        DESTINATION /usr/local/include)
install(FILES ${CMMH_THIRD_PARTY_DIR}/libcmmh.a
        DESTINATION /usr/local/lib)
install(FILES ${CMMH_THIRD_PARTY_DIR}/cmmh_driver
        DESTINATION /usr/local/bin)
install(FILES ${CMMH_THIRD_PARTY_DIR}/cmmh_driver.service
        DESTINATION /usr/lib/systemd/system)
