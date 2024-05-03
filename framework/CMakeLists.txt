set(SVKFramework_INCLUDE_DEST "include/")
set(SVKFramework_LIB_DEST "lib64/")

set(SVKFramework_SRC ${CMAKE_CURRENT_SOURCE_DIR}/src/framework.cc)
set(SVKFramework_INC ${CMAKE_CURRENT_SOURCE_DIR}/include/framework_upstream.h
        ${CMAKE_CURRENT_SOURCE_DIR}/include/framework_struct.h
        ${CMAKE_CURRENT_SOURCE_DIR}/include/framework_downstream.h
        ${CMAKE_CURRENT_SOURCE_DIR}/src/include_private/framework_service.hpp
        ${CMAKE_SOURCE_DIR}/common/include/svk_logger.h)




if(BUILD_SHARED_LIBS)
    add_library(${SVKFramework} SHARED ${SVKFramework_SRC} ${SVKFramework_INC})
else() 
    add_library(${SVKFramework} STATIC ${SVKFramework_SRC} ${SVKFramework_INC})
endif()

target_include_directories(${SVKFramework} PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src/include_private>
        $<BUILD_INTERFACE:${CMAKE_SOURCE_DIR}/common/include>
        $<INSTALL_INTERFACE:include>
        )
target_link_directories(${SVKFramework} PRIVATE ${CMAKE_SOURCE_DIR}/build/common)
target_link_libraries(${SVKFramework} svklogger)

install(
    TARGETS ${SVKFramework}
    # name of the CMake "export group" containing the targets we want to install
    EXPORT SVKFrameworkTargets
    # Dynamic, static library and include destination locations after running
    # "make install"
    LIBRARY DESTINATION ${SVKFramework_LIB_DEST}
    ARCHIVE DESTINATION ${SVKFramework_LIB_DEST} 
    INCLUDES DESTINATION ${SVKFramework_INCLUDE_DEST}
    )


install(FILES ${SVKFramework_INC} DESTINATION ${SVKFramework_INCLUDE_DEST})

set_target_properties(${SVKFramework} PROPERTIES 
                            VERSION ${PROJECT_VERSION}
                            SOVERSION ${PROJECT_VERSION_MAJOR})

set(SVKFramework_CMAKE_DEST "cmake/")

install(
    # The export we want to save (matches name defined above containing the
    # install targets)
    EXPORT SVKFrameworkTargets
    # CMake file in which to store the export's information
    FILE  SVKFrameworkTargets.cmake
    # Namespace prepends all targets in the export (when we import later, we
    # will use SVKFramework::SVKFramework)
    # NAMESPACE SVKFramework::
    # where to place the resulting file (here, we're putting it with the library)
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/${SVKFramework_CMAKE_DEST}
    )
