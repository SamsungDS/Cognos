# Collect source files
file(GLOB SOURCES *.cc)
file(GLOB HEADERS include/*.h)

# Create a library
add_library(cxl ${SOURCES} ${HEADERS})

target_include_directories(cxl PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include/ ${SVKFRAMEWORK_INCLUDE_DIRS} ${FMAPI_INCLUDE_PATH})
target_link_directories(cxl PRIVATE "${FMAPI_INCLUDE_PATH}/build")


#add an executable target linked with library
target_link_libraries(cxl mbox_a1_shared jansson)
install(FILES ${HEADERS} DESTINATION ${SVKCXL_INCLUDE_DEST})
install(
    TARGETS cxl
    EXPORT cxlTargets
    # name of the CMake "export group" containing the targets we want to install
    LIBRARY DESTINATION ${SVKCXL_LIB_DEST}
    INCLUDES DESTINATION "${SVKCXL_INCLUDE_DEST}"
)
