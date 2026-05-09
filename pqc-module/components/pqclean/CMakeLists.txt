cmake_minimum_required(VERSION 3.16)

#
# PQClean component for ESP-IDF.
#
# Add PQClean as a git submodule first:
#   git submodule add https://github.com/PQClean/PQClean.git \
#       components/pqclean/PQClean
#
# Then the sources below will be found at:
#   components/pqclean/PQClean/crypto_kem/kyber512/clean/*.c
#   components/pqclean/PQClean/crypto_sign/dilithium2/clean/*.c
#
# The randombytes shim in this directory replaces PQClean's randombytes.h.
#

set(PQCLEAN_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/PQClean")

idf_component_register(
    SRCS
        # ── ML-KEM-512 (Kyber512 clean reference) ──────────────────────────
        "${PQCLEAN_ROOT}/crypto_kem/kyber512/clean/cbd.c"
        "${PQCLEAN_ROOT}/crypto_kem/kyber512/clean/indcpa.c"
        "${PQCLEAN_ROOT}/crypto_kem/kyber512/clean/kem.c"
        "${PQCLEAN_ROOT}/crypto_kem/kyber512/clean/ntt.c"
        "${PQCLEAN_ROOT}/crypto_kem/kyber512/clean/poly.c"
        "${PQCLEAN_ROOT}/crypto_kem/kyber512/clean/polyvec.c"
        "${PQCLEAN_ROOT}/crypto_kem/kyber512/clean/reduce.c"
        "${PQCLEAN_ROOT}/crypto_kem/kyber512/clean/symmetric-shake.c"
        "${PQCLEAN_ROOT}/crypto_kem/kyber512/clean/verify.c"
        # ── ML-DSA-44 (Dilithium2 clean reference) ─────────────────────────
        "${PQCLEAN_ROOT}/crypto_sign/dilithium2/clean/ntt.c"
        "${PQCLEAN_ROOT}/crypto_sign/dilithium2/clean/packing.c"
        "${PQCLEAN_ROOT}/crypto_sign/dilithium2/clean/poly.c"
        "${PQCLEAN_ROOT}/crypto_sign/dilithium2/clean/polyvec.c"
        "${PQCLEAN_ROOT}/crypto_sign/dilithium2/clean/reduce.c"
        "${PQCLEAN_ROOT}/crypto_sign/dilithium2/clean/rounding.c"
        "${PQCLEAN_ROOT}/crypto_sign/dilithium2/clean/sign.c"
        "${PQCLEAN_ROOT}/crypto_sign/dilithium2/clean/symmetric-shake.c"
        # ── ESP32 randombytes shim (replaces PQClean's randombytes.h) ───────
        "randombytes_esp32.cpp"
    INCLUDE_DIRS
        "${PQCLEAN_ROOT}/crypto_kem/kyber512/clean"
        "${PQCLEAN_ROOT}/crypto_sign/dilithium2/clean"
        "${PQCLEAN_ROOT}/common"
        "."                              # exposes randombytes.h
    REQUIRES
        esp_hw_support                   # esp_fill_random
)

# PQClean requires C99 and has intentional unused-variable patterns.
target_compile_options(${COMPONENT_LIB} PRIVATE
    -std=c99
    -Wno-unused-variable
    -Wno-unused-function
    -O2                                  # important: -O0 is too slow for sign()
)
