
set(SVKSlatLogicLib_SRC sample_logic.cc)

set(SVKSlatLogicLib "svkslatsamplelogic")
set(SVKSlatLogicLib_LIB_DEST "lib64/")


add_library(${SVKSlatLogicLib} SHARED ${SVKSlatLogicLib_SRC})
target_link_directories(${SVKSlatLogicLib} PUBLIC ${SVKFW_LIBRARY_DIRS})
target_link_libraries(${SVKSlatLogicLib} PUBLIC svklogger)
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)

set_target_properties(${SVKSlatLogicLib} PROPERTIES
                        VERSION ${PROJECT_VERSION}
                        SOVERSION ${PROJECT_VERSION_MAJOR})

install(
    TARGETS ${SVKSlatLogicLib}
    LIBRARY DESTINATION ${SVKSlatLogicLib_LIB_DEST}
)

