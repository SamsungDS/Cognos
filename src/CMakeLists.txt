# Collect source files
file(GLOB SOURCES *.cc)
file(GLOB HEADERS include/*.h)

# Create a library
add_library(svkme ${SOURCES} ${HEADERS})
find_package(nlohmann_json REQUIRED)

target_include_directories(svkme PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include/" ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS})
target_link_directories(svkme PRIVATE ${SVKMGMTFW_LIB_DIRS} ${SVKFRAMEWORK_LIBRARY_DIRS})
target_link_libraries(svkme svklogger svkframework nlohmann_json)

add_definitions("-DBOOST_ALLOW_DEPRECATED_HEADERS")
add_definitions("-DBOOST_BIND_GLOBAL_PLACEHOLDERS")

set(SVKME_SRC_INCLUDE "${CMAKE_CURRENT_SOURCE_DIR}/include/")
set(SVKME_SRC_PATH "${CMAKE_CURRENT_SOURCE_DIR}/")
add_subdirectory("profilers")
add_subdirectory("movers")

if(BUILD_TESTING)
  add_definitions(-DTEST_BUILD=1 )
else()
  add_definitions(-DTEST_BUILD=0 )
endif()
install(FILES ${HEADERS} DESTINATION ${SVKME_INCLUDE_DEST})
install(
    TARGETS svkme
    EXPORT svkmeTargets
    # name of the CMake "export group" containing the targets we want to install
    LIBRARY DESTINATION ${SVKME_LIB_DEST}
)
