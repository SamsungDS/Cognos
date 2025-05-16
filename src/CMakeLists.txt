
include(FetchContent)
FetchContent_Declare(json URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz)
FetchContent_MakeAvailable(json)

set(SRCS ${CMAKE_CURRENT_SOURCE_DIR}/node_info.cc)

add_library(${PROJECT_NAME} SHARED ${SRCS} ${CMAKE_SOURCE_DIR}/include/node_info.hpp ${CMAKE_SOURCE_DIR}/src/include_private/helper_fns.hpp)

set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC")
set_target_properties(${PROJECT_NAME} PROPERTIES
                        VERSION ${PROJECT_VERSION}
                        SOVERSION ${PROJECT_VERSION_MAJOR})
target_include_directories(${PROJECT_NAME} PUBLIC ${PARENT_DIR}/include ${PARENT_DIR}/src/include_private ${SVKFRAMEWORK_INCLUDE_DIRS})

target_link_libraries(${PROJECT_NAME} PUBLIC "-lsvklogger")
target_link_libraries(${PROJECT_NAME} PUBLIC nlohmann_json::nlohmann_json)
target_link_directories(${PROJECT_NAME} PUBLIC ${SVKFRAMEWORK_LIBRARY_DIRS})

if(BUILD_TESTING)
    set_target_properties(${PROJECT_NAME} PROPERTIES COMPILE_DEFINITIONS "BUILD_TESTING")
endif()

install(
    TARGETS ${PROJECT_NAME}

    EXPORT ${PROJECT_NAME}Targets

    LIBRARY DESTINATION ${SVK_NODE_FEATURE_LIB_DEST}
    ARCHIVE DESTINATION ${SVK_NODE_FEATURE_LIB_DEST}
    INCLUDES DESTINATION ${SVK_NODE_FEATURE_INCLUDE_DEST}
)

install(
    FILES
    "${CMAKE_CURRENT_SOURCE_DIR}/node_info/find_node_info.py"
    DESTINATION "scripts/"
    )


