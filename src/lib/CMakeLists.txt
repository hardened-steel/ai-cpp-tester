cmake_minimum_required(VERSION 4.1)
project(foo-lib LANGUAGES CXX)

add_library(${PROJECT_NAME}
    box.hpp
    box.cpp
    empty.cpp
)
set_target_properties(${PROJECT_NAME}
    PROPERTIES
        CXX_STANDARD 20
        CXX_STANDARD_REQUIRED YES
        CXX_EXTENSIONS YES
        C_STANDARD 11
        C_STANDARD_REQUIRED YES
        C_EXTENSIONS YES
)
target_include_directories(${PROJECT_NAME} PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/../)
target_compile_definitions(${PROJECT_NAME} PUBLIC FOO BAR)
target_compile_options(${PROJECT_NAME} PUBLIC "-DBAZ -DBAX")
ai_test(${PROJECT_NAME} box.test.txt)