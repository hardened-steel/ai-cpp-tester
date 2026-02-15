cmake_minimum_required(VERSION 4.1)
project(app-bin LANGUAGES CXX)

add_library(${PROJECT_NAME}
    main.cpp
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
target_link_libraries(${PROJECT_NAME} PUBLIC foo-lib)
ai_test(${PROJECT_NAME})
