set(SVKSlatLib_SRC ${CMAKE_SOURCE_DIR}/src/slat.cc)
set(INC_DIR ${CMAKE_SOURCE_DIR}/include/)

set(SVKSlatLib "svkslat")
set(SVKSlatLib_INCLUDE_DEST "include/")
set(SVKSlatLib_LIB_DEST "lib64/")

add_library(${SVKSlatLib} SHARED ${SVKSlatLib_SRC})
target_include_directories(${SVKSlatLib} PUBLIC ${INC_DIR})
target_link_directories(${SVKSlatLib} PUBLIC ${SVKFW_LIBRARY_DIRS})
target_link_libraries(${SVKSlatLib} PUBLIC svklogger)
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)

set_target_properties(${SVKSlatLib} PROPERTIES 
                        VERSION ${PROJECT_VERSION} 
                        SOVERSION ${PROJECT_VERSION_MAJOR})

install(
    TARGETS ${SVKSlatLib}
    LIBRARY DESTINATION ${SVKSlatLib_LIB_DEST}
    INCLUDES DESTINATION ${SVKSlatLib_INCLUDE_DEST}
)

