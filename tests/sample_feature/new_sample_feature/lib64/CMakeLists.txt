set(NewSampleFeature_SRC ${CMAKE_CURRENT_SOURCE_DIR}/new_sample_feature.cc)
#set(NewSampleFeature_INC ${CMAKE_CURRENT_SOURCE_DIR}/../sample_feature.h)
set(NewSampleFeature_INSTALL_DEST "tests/sample_feature/new_sample_feature/lib64")
set(NewSampleFeature "svknew_sample_feature")
set(Framework_INC_DIR ${CMAKE_SOURCE_DIR}/framework/include)
set(NewSampleFeature_INC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../..)

add_library(${NewSampleFeature} SHARED ${NewSampleFeature_SRC} ${SampleFeature_INC})

target_include_directories(${NewSampleFeature} PUBLIC ${Framework_INC_DIR} ${NewSampleFeature_INC_DIR})

install(
    TARGETS ${NewSampleFeature}

    LIBRARY DESTINATION ${NewSampleFeature_INSTALL_DEST}
    INCLUDES DESTINATION ${NewSampleFeature_INSTALL_DEST}
)
