
set(SVKSlatLogicLib_SRC sample_logic.cc ${CMAKE_SOURCE_DIR}/thread_manager/worker.cc)
set(THREAD_MGR_INC_DIR ${CMAKE_SOURCE_DIR}/thread_manager/)

set(SVKSlatLogicLib "svkslatsamplelogic")
set(SVKSlatLogicLib_LIB_DEST "lib64/")


add_library(${SVKSlatLogicLib} SHARED ${SVKSlatLogicLib_SRC})
target_include_directories(${SVKSlatLogicLib} PUBLIC ${THREAD_MGR_INC_DIR})
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

