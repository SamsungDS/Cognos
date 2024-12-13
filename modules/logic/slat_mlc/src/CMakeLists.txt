set(SVKSlatMlcLogicLib_SRC  slat_run_bin.cc slat_mlc_exec.cc slat_mlc_logic.cc)
set(SVKSlatMlcLogicLib "svkslatmlclogic")

set(SVKSlatLogicLib_LIB_DEST "logic_modules/svkslatmlclogic/lib64/")

#TODO this should be used via config
file(COPY ${CMAKE_CURRENT_SOURCE_DIR}/../deps/mlc/Linux/mlc DESTINATION "/usr/local/svk/feature_modules/slat/logic_modules/svkslatmlclogic/bin/")

add_library(${SVKSlatMlcLogicLib} SHARED ${SVKSlatMlcLogicLib_SRC})
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