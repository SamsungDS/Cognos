add_subdirectory(conf)

add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)
add_executable(sample_app src/sample_app.cc)
target_include_directories(sample_app PUBLIC ${json_SOURCE_DIR}/include)
target_link_directories(sample_app PUBLIC ${SVKFW_LIBRARY_DIRS})

target_link_libraries(
  sample_app
  boost_program_options
  dl
  svkframework
  svklogger
  nlohmann_json::nlohmann_json
)

