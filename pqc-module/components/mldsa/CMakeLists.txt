cmake_minimum_required(VERSION 3.16)

#
# ML-DSA-44 component — pq-code-package/mldsa-native (FIPS 204).
#
# Clone the submodule first:
#   make submodule-mldsa   →  components/mldsa/mldsa-native
#
# fips202 is intentionally omitted here — it is provided by the mlkem
# component (identical PQCP implementation) to avoid duplicate symbol errors
# when both components are linked into the same binary.
#

set(MLDSA_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/mldsa-native")

idf_component_register(
    SRCS
        "${MLDSA_ROOT}/mldsa/src/ct.c"
        "${MLDSA_ROOT}/mldsa/src/debug.c"
        "${MLDSA_ROOT}/mldsa/src/packing.c"
        "${MLDSA_ROOT}/mldsa/src/poly.c"
        "${MLDSA_ROOT}/mldsa/src/poly_kl.c"
        "${MLDSA_ROOT}/mldsa/src/polyvec.c"
        "${MLDSA_ROOT}/mldsa/src/polyvec_lazy.c"
        "${MLDSA_ROOT}/mldsa/src/sign.c"
        "randombytes_esp32.cpp"
    INCLUDE_DIRS
        "${MLDSA_ROOT}/mldsa"       # mldsa_native.h (public API + size constants)
        "${MLDSA_ROOT}/mldsa/src"   # internal headers + fips202/ for sub-includes
        "."                         # randombytes.h
    REQUIRES
        mlkem           # provides fips202 implementation
        esp_hw_support  # esp_fill_random for randombytes shim
)

target_compile_options(${COMPONENT_LIB} PRIVATE
    -std=c99
    -O2
    -Wno-unused-variable
    -Wno-unused-function
    # Select ML-DSA-44 — exposes mldsa44_keypair, mldsa44_signature, mldsa44_verify
    -DMLD_CONFIG_PARAMETER_SET=44
)
