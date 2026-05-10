cmake_minimum_required(VERSION 3.16)

#
# ML-DSA-44 component — pq-code-package/mldsa-native (FIPS 204).
#
# Clone the submodule first:
#   make submodule-mldsa   →  components/mldsa/mldsa-native
#
# mldsa-native namespaces ALL its symbols with the parameter-set prefix
# (mldsa44_*), including its fips202 functions (mldsa44_shake128_absorb, etc.).
# This means mldsa's fips202 does NOT conflict with mlkem's fips202 —
# both are compiled and linked independently.
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
        "${MLDSA_ROOT}/mldsa/src/fips202/fips202.c"
        "${MLDSA_ROOT}/mldsa/src/fips202/fips202x4.c"
        "${MLDSA_ROOT}/mldsa/src/fips202/keccakf1600.c"
        "randombytes_esp32.cpp"
    INCLUDE_DIRS
        "${MLDSA_ROOT}/mldsa"       # mldsa_native.h (public API + size constants)
        "${MLDSA_ROOT}/mldsa/src"   # internal headers + fips202/ for sub-includes
        "."                         # randombytes.h
    REQUIRES
        esp_hw_support              # esp_fill_random for randombytes shim
)

target_compile_options(${COMPONENT_LIB} PRIVATE
    -std=c99
    -O2
    -Wno-unused-variable
    -Wno-unused-function
    # Select ML-DSA-44 and set namespace — exposes mldsa44_keypair, mldsa44_signature, mldsa44_verify
    -DMLD_CONFIG_PARAMETER_SET=44
    -DMLD_CONFIG_NAMESPACE_PREFIX=mldsa44
)
