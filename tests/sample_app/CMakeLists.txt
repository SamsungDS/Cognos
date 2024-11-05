add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)
add_executable(sample_app src/sample_app.cc)
target_link_directories(sample_app PUBLIC ${SVKFW_LIBRARY_DIRS})

target_link_libraries(
  sample_app
  boost_program_options
  dl
)

