find_package(Python REQUIRED)

function(ai_test)
    list(POP_FRONT ARGV TARGET)

    get_target_property(TARGET_SOURCES ${TARGET} SOURCES)
    get_target_property(TARGET_NAME ${TARGET} NAME)

    string(TOUPPER "${CMAKE_BUILD_TYPE}" CONFIG_TYPE)
    set(DEFAULT_FLAGS "${CMAKE_CXX_FLAGS_${CONFIG_TYPE}}")

    set(TARGET_INDEX_FILE ${CMAKE_CURRENT_BINARY_DIR}/${TARGET_NAME}.index.json)
    set(TARGET_EMBEDDINGS_FILE ${CMAKE_CURRENT_BINARY_DIR}/${TARGET_NAME}.embeddings.json)
    set(TARGET_TEST_SCENARIOS ${CMAKE_CURRENT_BINARY_DIR}/${TARGET_NAME}.scenarios.cpp)

    set(TARGET_INDEXES "")
    foreach(SOURCE IN LISTS TARGET_SOURCES)
        set(SOURCE_FILE ${CMAKE_CURRENT_SOURCE_DIR}/${SOURCE})
        set(INDEX_FILE ${CMAKE_CURRENT_BINARY_DIR}/${TARGET_NAME}.${SOURCE}.index.json)

        get_filename_component(FILE_EXT ${SOURCE} LAST_EXT)
        string(TOLOWER "${FILE_EXT}" FILE_EXT)

        set(IS_HEADER FALSE)
        if(FILE_EXT MATCHES "^\\.(h|hpp|hxx|hh|inl)$")
            set(IS_HEADER TRUE)
        endif()

        if (NOT ${IS_HEADER})
            add_custom_command(
                OUTPUT
                    ${INDEX_FILE}
                COMMAND
                    ${Python_EXECUTABLE} ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/cpp.index.py
                        "parse"
                        --src ${SOURCE_FILE}
                        --dst ${INDEX_FILE}
                        --flg ${DEFAULT_FLAGS}
                        --dep "${INDEX_FILE}.d"
                        --
                        "--std=c++$<TARGET_PROPERTY:${TARGET},CXX_STANDARD>"
                        "$<$<BOOL:$<TARGET_PROPERTY:${TARGET},INCLUDE_DIRECTORIES>>:-I$<JOIN:$<TARGET_PROPERTY:${TARGET},INCLUDE_DIRECTORIES>, -I>>"
                        "$<$<BOOL:$<TARGET_PROPERTY:${TARGET},COMPILE_DEFINITIONS>>:-D$<JOIN:$<TARGET_PROPERTY:${TARGET},COMPILE_DEFINITIONS>, -D>>"
                        "$<JOIN:$<TARGET_PROPERTY:${TARGET},COMPILE_OPTIONS>, >"
                        "$<JOIN:$<TARGET_PROPERTY:${TARGET},COMPILE_FLAGS>, >"
                DEPENDS
                    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/cpp.index.py ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/ai.test.cmake ${SOURCE_FILE} ${TARGET}
                DEPFILE "${INDEX_FILE}.d"
                VERBATIM
            )
            list(APPEND TARGET_INDEXES "${INDEX_FILE}")
        endif()
    endforeach()

    add_custom_target(
        ${TARGET_NAME}.index
        COMMAND
            ${Python_EXECUTABLE} ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/cpp.index.py
                "merge"
                --inputs ${TARGET_INDEXES}
                --output ${TARGET_INDEX_FILE}
        DEPENDS
            ${TARGET_INDEXES}
        VERBATIM
    )

    add_custom_command(
        OUTPUT
            ${TARGET_EMBEDDINGS_FILE}
        COMMAND
            ${Python_EXECUTABLE} ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/cpp.embedding.py ${TARGET_INDEX_FILE} ${TARGET_EMBEDDINGS_FILE}
        DEPENDS
            ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/cpp.embedding.py
            ${TARGET_INDEX_FILE}
    )
    add_custom_target(
        ${TARGET_NAME}.embeddings
        DEPENDS
            ${TARGET_EMBEDDINGS_FILE}
    )

    add_custom_command(
        OUTPUT
            ${TARGET_TEST_SCENARIOS}
        COMMAND
            ${Python_EXECUTABLE} ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/ai.tester.py
                --embeddings ${TARGET_EMBEDDINGS_FILE}
                --index ${TARGET_INDEX_FILE}
                --scenario ${TARGET_TEST_SCENARIOS}
                ${ARGV}
        DEPENDS
            ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/ai.tester.py
            ${TARGET_EMBEDDINGS_FILE}
            ${TARGET_INDEX_FILE}
    )
    add_executable(${TARGET_NAME}.test ${TARGET_TEST_SCENARIOS})
    target_link_libraries(${TARGET_NAME}.test PRIVATE ${TARGET})
    add_test(${TARGET_NAME}.test COMMAND ${TARGET_NAME}.test WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
endfunction()
