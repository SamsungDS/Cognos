cmake_minimum_required(VERSION 3.7)

find_package(PkgConfig REQUIRED)
pkg_check_modules(SVKFRAMEWORK REQUIRED svkframework)

include(${CMAKE_SOURCE_DIR}/cmake/svk_global.cmake)

# Set this project's name.
set(SVK_CXL_VERSION ${GIT_REPO_VERSION})
set(SVKCXL "svkcxl")
project(${SVKCXL} VERSION ${SVK_CXL_VERSION}
	DESCRIPTION "SVK CXL")

include(GNUInstallDirs)

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
configure_file("cmake/${SVKCXL}.pc.in" "${pkg_config}" @ONLY)

find_package(PkgConfig REQUIRED)
pkg_check_modules(SVKFRAMEWORK REQUIRED svkframework)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -rdynamic")

# Include custom cmake modules
list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake")

# Set coverage flags for GCC/Clang
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    if(WITH_COVERAGE)
        message(STATUS "Building with coverage")
        set(COVERAGE_FLAGS "--coverage -fprofile-arcs -ftest-coverage")
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${COVERAGE_FLAGS}")
        set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} ${COVERAGE_FLAGS}")
    endif()
endif()

# Add subdirectories
add_subdirectory(src)
if(BUILD_TESTING)
    add_subdirectory(tests)
endif()

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
    file(WRITE \"/etc/ld.so.conf.d/svk-cxl-x86_64.conf\" \"\\n${CMAKE_INSTALL_PREFIX}/lib\\n\")
    file(APPEND \"/etc/ld.so.conf.d/svk-cxl-x86_64.conf\" \"\\n${CMAKE_INSTALL_PREFIX}/lib64\\n\")
")

if(WITH_FMAPI)
    install(CODE "
        file(APPEND \"/etc/ld.so.conf.d/svk-cxl-x86_64.conf\" \"\\n${FMAPI_INCLUDE_PATH}/build\\n\")
    ")
    install(
        FILES "${FMAPI_LIBRARY_PATH}"
        DESTINATION "/usr/local/lib/cxl_memory_box"
    )
    install(
        FILES "config/cxl.conf"
        DESTINATION "${SVKMGMTFW_DIRS}"
    )
    if(MOCK_FLAG)
        install(
            FILES "${FMAPI_INCLUDE_PATH}/sample_json/input.json"
            DESTINATION "${SVKMGMTFW_DIRS}"
        )
    endif()
endif()

install(
    FILES "config/zmq_config.json"
    DESTINATION "/etc/svk/"
)
# install pkg config file
install(
    FILES "${pkg_config}"
    DESTINATION "${pkgconfig_install_dir}"
)
