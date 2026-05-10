idf_component_register(INCLUDE_DIRS "../../liboqs_src/build/include")

add_prebuilt_library(oqs_lib "../../liboqs_src/build/lib/liboqs.a" REQUIRES mbedtls)
target_link_libraries(${COMPONENT_LIB} INTERFACE oqs_lib)
