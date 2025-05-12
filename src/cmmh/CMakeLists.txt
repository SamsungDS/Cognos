# Set the plugin name
set(PLUGIN_NAME cmmh)

file(GLOB CMMH_SOURCES "*.cc")
file(GLOB CMMH_HEADERS "include/*.h")


find_library(PCI_LIB NAMES pci REQUIRED)
if(NOT PCI_LIB)
  message(FATAL_ERROR "libpci not found. Install required dev packages.")
else()
	message(STATUS "found libpci: ${PCI_LIB}")
endif()

add_library(${PLUGIN_NAME} SHARED ${CMMH_SOURCES} ${CMMH_HEADERS})
add_dependencies(${PLUGIN_NAME} cxl)

target_include_directories(${PLUGIN_NAME} PRIVATE
"${CMAKE_CURRENT_SOURCE_DIR}/include"
"${PROJECT_SOURCE_DIR}/src/include"
${SVKMGMTFW_INCLUDE_DIRS}
${SVKFRAMEWORK_INCLUDE_DIRS}
)

target_link_directories(${PLUGIN_NAME} PRIVATE
${SVKMGMTFW_LIB_DIRS}
${SVKFRAMEWORK_LIBRARY_DIRS}
)

#force linker to retain libpci symbols
target_link_options(${PLUGIN_NAME} PRIVATE "-Wl,--no-as-needed")

# Link required system and framework libraries
target_link_libraries(${PLUGIN_NAME}
 PRIVATE      	
 numa
 svklogger
 ${PCI_LIB} 
 ${PROJECT_BINARY_DIR}/src/libcxl.so
)

# Install plugin .so to plugin directory
install(TARGETS ${PLUGIN_NAME}
 LIBRARY DESTINATION ${SVKCXL_LIB_DEST})

