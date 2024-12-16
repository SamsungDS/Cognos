set(SVKSlatMlcLogicLib_SRC  ${CMAKE_SOURCE_DIR}/src/logger_util.cc slat_run_bin.cc slat_mlc_exec.cc slat_mlc_logic.cc)
set(SVKSlatMlcLogicLib "mlclogic")

set(SVKSlatLogicLib_LIB_DEST "logic_modules/mlclogic/lib64/")


add_library(${SVKSlatMlcLogicLib} SHARED ${SVKSlatMlcLogicLib_SRC})
target_include_directories(${SVKSlatMlcLogicLib} PUBLIC ${CMAKE_SOURCE_DIR}/include)
target_link_directories(${SVKSlatMlcLogicLib} PUBLIC ${SVKFW_LIBRARY_DIRS})
target_link_libraries(${SVKSlatMlcLogicLib} PUBLIC svklogger)
target_link_libraries(${SVKSlatMlcLogicLib} PUBLIC boost_filesystem)
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)

set_target_properties(${SVKSlatMlcLogicLib} PROPERTIES
                        VERSION ${PROJECT_VERSION}
                        SOVERSION ${PROJECT_VERSION_MAJOR})

install(
    TARGETS ${SVKSlatMlcLogicLib}
    LIBRARY DESTINATION ${SVKSlatLogicLib_LIB_DEST}
)

install(
    FILES ${CMAKE_CURRENT_SOURCE_DIR}/../deps/mlc/Linux/redist.txt
    DESTINATION ${SVKSlatLogicLib_LIB_DEST}/../bin RENAME mlc_redist.txt
)

install (
    PROGRAMS ${CMAKE_CURRENT_SOURCE_DIR}/../deps/mlc/Linux/mlc
    DESTINATION ${SVKSlatLogicLib_LIB_DEST}/../bin
)