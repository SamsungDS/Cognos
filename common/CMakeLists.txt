# Build shared libraries by default.
find_package(fmt REQUIRED)
find_package(spdlog REQUIRED)

set(SVKLogger "svklogger")
set(SVKLogger_INC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/include PARENT_SCOPE)
set(SVKLogger_SRC ${CMAKE_CURRENT_SOURCE_DIR}/src/svk_logger.cc)
set(SVKLogger_INC ${CMAKE_CURRENT_SOURCE_DIR}/include/svk_logger.h)

set(SVKLogger_INCLUDE_DEST "include/")
set(SVKLogger_CMAKE_DEST "cmake/")
set(SVKLogger_LIB_DEST "${CMAKE_INSTALL_LIBDIR}")

if(BUILD_SHARED_LIBS)
    add_library(${SVKLogger} SHARED ${SVKLogger_SRC} ${SVKLogger_INC})
else()
    add_library(${SVKLogger} STATIC ${SVKLogger_SRC} ${SVKLogger_INC})
endif()

target_include_directories(${SVKLogger} PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
        )

target_compile_definitions(${SVKLogger} PUBLIC "-DSPDLOG_FMT_EXTERNAL")
target_link_libraries(${SVKLogger} PUBLIC spdlog)

set_target_properties(${SVKLogger} PROPERTIES 
                            VERSION ${PROJECT_VERSION}
                            SOVERSION ${PROJECT_VERSION_MAJOR})

install(
    TARGETS ${SVKLogger}
    # name of the CMake "export group" containing the targets we want to install
    EXPORT SVKCommonTargets
    # Dynamic, static library and include destination locations after running
    # "make install"
    LIBRARY DESTINATION ${SVKLogger_LIB_DEST}
    ARCHIVE DESTINATION ${SVKLogger_LIB_DEST}
    INCLUDES DESTINATION ${SVKLogger_INCLUDE_DEST}
    )

install(FILES ${SVKLogger_INC} DESTINATION ${SVKLogger_INCLUDE_DEST})

install(
    # The export we want to save (matches name defined above containing the
    # install targets)
    EXPORT SVKCommonTargets
    # CMake file in which to store the export's information
    FILE  SVKCommonTargets.cmake
    # where to place the resulting file (here, we're putting it with the library)
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/${SVKLogger_CMAKE_DEST}
    )
