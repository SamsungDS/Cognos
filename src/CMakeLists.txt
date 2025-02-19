set(RAS_SRC ${CMAKE_CURRENT_SOURCE_DIR}/ras.cc)
set(RAS_INC ${CMAKE_CURRENT_SOURCE_DIR}/../include/ras.hpp )
set(RAS_LIB_DEST "lib64/")
set(RAS_INCLUDE_DEST "include/")
set(RAS "ras")

include_directories(${CMAKE_CURRENT_SOURCE_DIR}/../include)
add_library(${RAS} SHARED ${RAS_SRC} ${RAS_INC})
target_include_directories(${RAS} PUBLIC ${RAS_INCLUDE_DEST})
target_link_directories(${RAS} PUBLIC ${SVKFW_LIBRARY_DIRS})
target_link_libraries(
  ${RAS}
  svkframework
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
    INCLUDES DESTINATION ${RAS_INCLUDE_DEST}
)

install(FILES ${RAS_INC} DESTINATION ${RAS_INCLUDE_DEST})

