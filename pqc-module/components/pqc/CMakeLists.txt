cmake_minimum_required(VERSION 3.16)

idf_component_register(
    SRCS
        "pqc.cpp"
    INCLUDE_DIRS
        "include"
    REQUIRES
        mlkem
        mldsa
        nvs_flash
        mbedtls
        esp_hw_support
        esp_wifi
)
