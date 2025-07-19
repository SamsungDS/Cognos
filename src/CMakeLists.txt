set(RAS_SRC
  ${CMAKE_SOURCE_DIR}/src/utils/ras_json_validate.cpp
  ${CMAKE_SOURCE_DIR}/src/utils/logic_module_manager.cc
  ${CMAKE_CURRENT_SOURCE_DIR}/ras_request_handler.cc
  ${CMAKE_CURRENT_SOURCE_DIR}/ras_monitor.cc
  ${CMAKE_CURRENT_SOURCE_DIR}/ras.cc)
set(RAS_INC ${CMAKE_CURRENT_SOURCE_DIR}/../include/ras.hpp )
set(RAS_LIB_DEST "lib64/")
set(RAS_INCLUDE_DEST "include/")
set(RAS "ras")
set(RAS_LINK_LIBRARIES "stdc++fs fmt nlohmann_json::nlohmann_json")
add_subdirectory(utils)

include_directories(${CMAKE_CURRENT_SOURCE_DIR}/../include)
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/utils/rte_ring)
add_library(${RAS} SHARED ${RAS_SRC} ${RAS_INC})
add_dependencies(${RAS} rte_ring ${LIBMOCK})
target_include_directories(${RAS} PUBLIC ${RAS_INCLUDE_DEST})
target_link_directories(${RAS} PUBLIC ${SVKFW_LIBRARY_DIRS} ${RAS_LINK_LIBRARIES})
target_link_libraries(
  ${RAS}
  svkframework
  rte_ring
  dl
  svklogger
)

set_target_properties(${RAS} PROPERTIES 
                        VERSION ${SVK_RAS_VERSION_FULL} 
                        SOVERSION ${SVK_RAS_VERSION})

install(
    TARGETS ${RAS}
    LIBRARY DESTINATION ${RAS_LIB_DEST}
    ARCHIVE DESTINATION ${RAS_INSTALL_DEST}
    PUBLIC_HEADER DESTINATION ${RAS_INCLUDE_DEST}
)

install(FILES ${RAS_INC} DESTINATION ${RAS_INCLUDE_DEST} COMPONENT dev)

