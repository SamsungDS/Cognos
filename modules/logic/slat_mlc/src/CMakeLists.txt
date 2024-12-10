set(SVKSlatMlcLogicLib_SRC  slat_run_bin.cc slat_mlc_exec.cc slat_mlc_logic.cc)
set(SVKSlatMlcLogicLib "svkslatmlclogic")

set(SVKSlatLogicLib_LIB_DEST "lib64/")

file(COPY ${CMAKE_CURRENT_SOURCE_DIR}/../deps/mlc/Linux/mlc DESTINATION /usr/svk/slat/logic/mlc/deps/mlc/Linux/)
add_library(${SVKSlatMlcLogicLib} SHARED ${SVKSlatMlcLogicLib_SRC})
target_link_directories(${SVKSlatMlcLogicLib} PUBLIC ${SVKFW_LIBRARY_DIRS})
target_link_libraries(${SVKSlatMlcLogicLib} PUBLIC svklogger)
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)

set_target_properties(${SVKSlatMlcLogicLib} PROPERTIES
                        VERSION ${PROJECT_VERSION}
                        SOVERSION ${PROJECT_VERSION_MAJOR})

install(
    TARGETS ${SVKSlatMlcLogicLib}
    LIBRARY DESTINATION ${SVKSlatLogicLib_LIB_DEST}
)