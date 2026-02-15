cmake_minimum_required(VERSION 4.1)
project(test-cpp-project LANGUAGES CXX C VERSION 0.0.1)

include(ai.test.cmake)
add_subdirectory(src/lib)
add_subdirectory(src/app)
