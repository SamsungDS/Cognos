cmake_minimum_required(VERSION 3.7)

find_package(PkgConfig REQUIRED)
pkg_check_modules(SVKFRAMEWORK REQUIRED svkframework)

include(${CMAKE_SOURCE_DIR}/cmake/svk_global.cmake)

# Set this project's name.
set(SVK_CME_VERSION ${GIT_REPO_VERSION})
set(SVKCME "svkcme")
project(${SVKCME} VERSION ${SVK_CME_VERSION}
	DESCRIPTION "SVK CME")

include(GNUInstallDirs)

option(BUILD_SHARED_LIBS "Generate shared libs" ON)

set(PKG_CONFIG_INCLUDEDIR "\${prefix}/${CMAKE_INSTALL_INCLUDEDIR}")
set(PKG_CONFIG_LIBDIR "\${exec_prefix}/${CMAKE_INSTALL_LIBDIR}")
set(pkg_config "${CMAKE_BINARY_DIR}/${SVKCME}.pc")
set(pkgconfig_install_dir "${CMAKE_INSTALL_LIBDIR}/pkgconfig")
set(SVKCME_LIB_DEST "lib64/")
set(SVKCME_INCLUDE_DEST "include/")
set(SVKMGMTFW_DIRS "/usr/local/svk/mgmt-fw")
set(SVKMGMTFW_INCLUDE_DIRS "/usr/local/svk/mgmt-fw/include")
set(SVKMGMTFW_LIB_DIRS "/usr/local/svk/mgmt-fw/lib64")
configure_file("cmake/${SVKCME}.pc.in" "${pkg_config}" @ONLY)

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
	SVKCMEConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY AnyNewerVersion
    )

    set(SVKCME_CMAKE_DEST "cmake/")

install(
    FILES
	"${CMAKE_CURRENT_BINARY_DIR}/SVKCMEConfigVersion.cmake"
	DESTINATION ${CMAKE_INSTALL_LIBDIR}/${SVKCME_CMAKE_DEST}
    )

install(
    DESTINATION "/etc/ld.so.conf.d"
)

install(
    FILES "config/damo_config.json"
    DESTINATION "/etc/svk/"
)
install(
    FILES "tools/tm_gen_config.py"
    DESTINATION "/etc/svk/"
)
# install pkg config file
install(
    FILES "${pkg_config}"
    DESTINATION "${pkgconfig_install_dir}"
)
