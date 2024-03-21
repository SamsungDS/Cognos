set(SampleFeature_SRC ${CMAKE_CURRENT_SOURCE_DIR}/sample_feature.cc)
set(SampleFeature_INC ${CMAKE_CURRENT_SOURCE_DIR}/sample_feature.h)
set(SampleFeatureName "sample_feature")
set(Framework_INC_DIR ${CMAKE_SOURCE_DIR}/framework/include)

include_directories(${Framework_INC_DIR})
add_library(${SampleFeatureName} SHARED ${SampleFeature_SRC} ${SampleFeature_INC})
