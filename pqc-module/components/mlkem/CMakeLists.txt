cmake_minimum_required(VERSION 3.16)

#
# ML-KEM-512 component — pq-code-package/mlkem-native (FIPS 203).
#
# Clone the submodule first:
#   make submodule-mlkem   →  components/mlkem/mlkem-native
#
# Sources use the portable C backend only (no aarch64/x86 intrinsics —
# ESP32 Xtensa has neither).  fips202 is compiled here and shared with the
# mldsa component via REQUIRES.
#

set(MLKEM_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/mlkem-native")

idf_component_register(
    SRCS
        "${MLKEM_ROOT}/mlkem/src/compress.c"
        "${MLKEM_ROOT}/mlkem/src/debug.c"
        "${MLKEM_ROOT}/mlkem/src/indcpa.c"
        "${MLKEM_ROOT}/mlkem/src/kem.c"
        "${MLKEM_ROOT}/mlkem/src/poly.c"
        "${MLKEM_ROOT}/mlkem/src/poly_k.c"
        "${MLKEM_ROOT}/mlkem/src/sampling.c"
        "${MLKEM_ROOT}/mlkem/src/verify.c"
        "${MLKEM_ROOT}/mlkem/src/fips202/fips202.c"
        "${MLKEM_ROOT}/mlkem/src/fips202/fips202x4.c"
        "${MLKEM_ROOT}/mlkem/src/fips202/keccakf1600.c"
    INCLUDE_DIRS
        "${MLKEM_ROOT}/mlkem"       # mlkem_native.h (public API + size constants)
        "${MLKEM_ROOT}/mlkem/src"   # internal headers + fips202/ for sub-includes
    REQUIRES
        esp_hw_support
)

target_compile_options(${COMPONENT_LIB} PRIVATE
    -std=c99
    -O2
    -Wno-unused-function
    # Select ML-KEM-512 — exposes mlkem512_keypair, mlkem512_enc, mlkem512_enc_derand
    -DMLK_CONFIG_PARAMETER_SET=512
)
