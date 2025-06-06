# Set the plugin name
set(PLUGIN_NAME cmmh)

set(CMMH_STATIC_LIB "${PROJECT_SOURCE_DIR}/third_party/libcmmh.a")
if(NOT EXISTS ${CMMH_STATIC_LIB})
 message(FATAL_ERROR "libcmmh.a not found at ${CMMH_STATIC_LIB}")
endif()

file(GLOB CMMH_SOURCES "*.cc")
file(GLOB CMMH_HEADERS "include/*.h")


find_library(PCI_LIB NAMES pci REQUIRED)
if(NOT PCI_LIB)
  message(FATAL_ERROR "libpci not found. Install required dev packages.")
else()
	message(STATUS "found libpci: ${PCI_LIB}")
endif()

add_library(${PLUGIN_NAME} SHARED ${CMMH_SOURCES} ${CMMH_HEADERS})
add_dependencies(${PLUGIN_NAME} svkcxl)

target_include_directories(${PLUGIN_NAME} PRIVATE
"${CMAKE_CURRENT_SOURCE_DIR}/include"
"${PROJECT_SOURCE_DIR}/src/include"
${SVKMGMTFW_INCLUDE_DIRS}
${SVKFRAMEWORK_INCLUDE_DIRS}
)

target_link_directories(${PLUGIN_NAME} PRIVATE
${SVKMGMTFW_LIB_DIRS}
${SVKFRAMEWORK_LIBRARY_DIRS}
"${PROJECT_SOURCE_DIR}/third_party"
)

#force linker to retain libpci symbols
target_link_options(${PLUGIN_NAME} PRIVATE "-Wl,--no-as-needed")

# Link required system and framework libraries
target_link_libraries(${PLUGIN_NAME}
 PRIVATE      
 "-Wl,--whole-archive"  
 ${CMMH_STATIC_LIB}
 "-Wl,--no-whole-archive"  
 numa
 svklogger
 ${PCI_LIB} 
 ${PROJECT_BINARY_DIR}/src/libsvkcxl.so
)

install(TARGETS ${PLUGIN_NAME} 
LIBRARY DESTINATION "${CMMH_LIB_PATH}")


