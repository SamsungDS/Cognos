execute_process(
  COMMAND pkg-config --cflags svkframework
  OUTPUT_VARIABLE SVK_FW_CFLAGS
  OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${SVK_FW_CFLAGS}")
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)
link_directories(${CMAKE_SOURCE_DIR}/build/svc_mgr)

set(SampleService_SRC ${CMAKE_CURRENT_SOURCE_DIR}/pub.cc)
set(SampleService_INC ${CMAKE_CURRENT_SOURCE_DIR}/pub.h)
set(SampleService_INSTALL_DEST "tests/unit/svc_mgr/sample_service/")
set(SampleService "sample_service")
add_library(${SampleService} SHARED ${SampleService_SRC} ${SampleService_INC})

target_include_directories(${SampleService} PUBLIC ${SVC_MGR_INC_DIR} -lzmq
                                                   -lpthread -lsvklogger)

install(
  TARGETS ${SampleService}
  LIBRARY DESTINATION ${SampleService_INSTALL_DEST}
  INCLUDES
  DESTINATION ${SampleService_INSTALL_DEST})

install(FILES ${SampleService_INC} DESTINATION ${SampleService_INSTALL_DEST})
