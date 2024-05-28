
# Set the minimum required version of CMake for this project.
cmake_minimum_required(VERSION 3.7)

include(${CMAKE_SOURCE_DIR}/cmake/svk_global.cmake)

# Set this project's name.
set(SVK_FRAMEWORK_VERSION ${GIT_REPO_VERSION})
set(SVKFramework "svkframework")
project(${SVKFramework} VERSION ${SVK_FRAMEWORK_VERSION}
                        DESCRIPTION "SVK Framework")

include(GNUInstallDirs)
set(PKG_CONFIG_SPDLOG spdlog)

option(BUILD_SHARED_LIBS "Generate shared libs" ON)

set(PKG_CONFIG_INCLUDEDIR "\${prefix}/${CMAKE_INSTALL_INCLUDEDIR}")
set(PKG_CONFIG_LIBDIR "\${exec_prefix}/${CMAKE_INSTALL_LIBDIR}")
set(pkg_config "${CMAKE_BINARY_DIR}/${SVKFramework}.pc")
set(pkgconfig_install_dir "${CMAKE_INSTALL_LIBDIR}/pkgconfig")
configure_file("cmake/${SVKFramework}.pc.in" "${pkg_config}" @ONLY)

# Enable CTest for testing these code examples.
# include(CTest)

add_subdirectory(common)
add_subdirectory(framework)

# Build script makes it so that if release is used, then tests are turned off 
if(BUILD_TESTING)
    add_subdirectory(tests)
elseif(WITH_RELEASE)
    add_subdirectory(tests/sample_feature)
endif()

include(CMakePackageConfigHelpers)
write_basic_package_version_file(
    SVKFrameworkConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY AnyNewerVersion
    )

set(SVKFramework_CMAKE_DEST "cmake/")

install(
    FILES
        "cmake/svkframework-config.cmake"
        "${CMAKE_CURRENT_BINARY_DIR}/SVKFrameworkConfigVersion.cmake"
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/${SVKFramework_CMAKE_DEST}
    )

# install pkg config file
install(
    FILES "${pkg_config}"
    DESTINATION "${pkgconfig_install_dir}"
)
