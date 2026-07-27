cmake_minimum_required(VERSION 3.20)

project(mssclient VERSION 1.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS "-O3 -Wall")

find_package(CURL REQUIRED)
find_package(nlohmann_json REQUIRED)

add_library(mssclient STATIC src/mssclient.cpp)
target_include_directories(mssclient PUBLIC include)
target_link_libraries(mssclient PUBLIC CURL::libcurl nlohmann_json::nlohmann_json)

option(MSSCLIENT_BUILD_EXAMPLES "Build mssclient example programs" ON)
if(MSSCLIENT_BUILD_EXAMPLES)
  foreach(example pmt_example fpga_example led_example sensors_example)
    add_executable(${example} examples/${example}.cpp)
    target_link_libraries(${example} PRIVATE mssclient)
  endforeach()
endif()
