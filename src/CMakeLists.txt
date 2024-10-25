set(SVKSlatLib_SRC ${CMAKE_SOURCE_DIR}/src/slat.cc)
set(INC_DIR ${CMAKE_SOURCE_DIR}/include/)

set(SVKSlatLib "svkslat")
set(SVKSlatLib_INCLUDE_DEST "include/")
set(SVKSlatLib_LIB_DEST "lib64/")


execute_process(COMMAND pkg-config --cflags svkframework OUTPUT_VARIABLE SVK_FW_CFLAGS OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
execute_process(COMMAND pkg-config --libs svkframework OUTPUT_VARIABLE SVK_FW_LIBS OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)

set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC ${SVK_FW_CFLAGS}")

add_library(${SVKSlatLib} SHARED ${SVKSlatLib_SRC})
target_include_directories(${SVKSlatLib} PUBLIC ${INC_DIR})
target_link_libraries(${SVKSlatLib} PUBLIC "${SVK_FW_LIBS}" "svklogger")
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)

set_target_properties(${SVKSlatLib} PROPERTIES 
                        VERSION ${PROJECT_VERSION} 
                        SOVERSION ${PROJECT_VERSION_MAJOR})

install(
    TARGETS ${SVKSlatLib}
    LIBRARY DESTINATION ${SVKSlatLib_LIB_DEST}
    INCLUDES DESTINATION ${SVKSlatLib_INCLUDE_DEST}
)

