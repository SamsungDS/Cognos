set(SampleFeature_SRC ${CMAKE_CURRENT_SOURCE_DIR}/sample_feature.cc)
set(NewSampleFeature_SRC ${CMAKE_CURRENT_SOURCE_DIR}/new_sample_feature.cc)
set(SampleFeature_INC ${CMAKE_CURRENT_SOURCE_DIR}/sample_feature.h)
set(SampleFeature_INSTALL_DEST "tests/sample_feature/")
set(SampleFeature "sample_feature")
set(NewSampleFeature "svknew_sample_feature")
set(Framework_INC_DIR ${CMAKE_SOURCE_DIR}/framework/include)


add_library(${SampleFeature} SHARED ${SampleFeature_SRC} ${SampleFeature_INC})
add_library(${NewSampleFeature} SHARED ${NewSampleFeature_SRC} ${SampleFeature_INC})

target_include_directories(${SampleFeature} PUBLIC ${Framework_INC_DIR})
target_include_directories(${NewSampleFeature} PUBLIC ${Framework_INC_DIR})

install(
    TARGETS ${SampleFeature} ${NewSampleFeature}

    LIBRARY DESTINATION ${SampleFeature_INSTALL_DEST}
    INCLUDES DESTINATION ${SampleFeature_INSTALL_DEST}
)

install(FILES ${SampleFeature_INC} DESTINATION ${SampleFeature_INSTALL_DEST})
