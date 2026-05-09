cmake_minimum_required(VERSION 3.16)

#
# pqcp component — PQ Code Package implementations of ML-KEM-512 and ML-DSA-44.
#
# Clone submodules before building:
#   make submodule-mlkem   →  components/mlkem/mlkem-native
#   make submodule-mldsa   →  components/mldsa/mldsa-native
#
# fips202 is compiled once from mlkem-native and reused by mldsa-native to avoid
# duplicate symbol errors when both are compiled into the same component library.
# Both PQCP libraries use an identical fips202 public API.
#

set(MLKEM_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../mlkem/mlkem-native")
set(MLDSA_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../mldsa/mldsa-native")

idf_component_register(
    SRCS
        # ── ML-KEM-512 (mlkem-native, portable C, no arch-specific backend) ─
        "${MLKEM_ROOT}/mlkem/src/compress.c"
        "${MLKEM_ROOT}/mlkem/src/debug.c"
        "${MLKEM_ROOT}/mlkem/src/indcpa.c"
        "${MLKEM_ROOT}/mlkem/src/kem.c"
        "${MLKEM_ROOT}/mlkem/src/poly.c"
        "${MLKEM_ROOT}/mlkem/src/poly_k.c"
        "${MLKEM_ROOT}/mlkem/src/sampling.c"
        "${MLKEM_ROOT}/mlkem/src/verify.c"
        # fips202 compiled once — shared with ML-DSA below (identical API)
        "${MLKEM_ROOT}/mlkem/src/fips202/fips202.c"
        "${MLKEM_ROOT}/mlkem/src/fips202/fips202x4.c"
        "${MLKEM_ROOT}/mlkem/src/fips202/keccakf1600.c"
        # ── ML-DSA-44 (mldsa-native, portable C, no arch-specific backend) ──
        # fips202 intentionally omitted — provided by mlkem-native above
        "${MLDSA_ROOT}/mldsa/src/ct.c"
        "${MLDSA_ROOT}/mldsa/src/debug.c"
        "${MLDSA_ROOT}/mldsa/src/packing.c"
        "${MLDSA_ROOT}/mldsa/src/poly.c"
        "${MLDSA_ROOT}/mldsa/src/poly_kl.c"
        "${MLDSA_ROOT}/mldsa/src/polyvec.c"
        "${MLDSA_ROOT}/mldsa/src/polyvec_lazy.c"
        "${MLDSA_ROOT}/mldsa/src/sign.c"
        # ── ESP32 randombytes shim (feeds esp_fill_random into PQCP libs) ───
        "randombytes_esp32.cpp"
    INCLUDE_DIRS
        "${MLKEM_ROOT}/mlkem"        # mlkem_native.h
        "${MLKEM_ROOT}/mlkem/src"    # resolves "fips202/fips202.h" for mlkem sources
        "${MLDSA_ROOT}/mldsa"        # mldsa_native.h
        "${MLDSA_ROOT}/mldsa/src"    # resolves "fips202/fips202.h" for mldsa sources
        "."                          # randombytes.h
    REQUIRES
        esp_hw_support               # esp_fill_random
)

target_compile_options(${COMPONENT_LIB} PRIVATE
    -std=c99
    # Select ML-KEM-512 (FIPS 203) — exposes mlkem512_enc, mlkem512_enc_derand, etc.
    -DMLK_CONFIG_PARAMETER_SET=512
    # Select ML-DSA-44 (FIPS 204) — exposes mldsa44_keypair, mldsa44_signature, etc.
    -DMLD_CONFIG_PARAMETER_SET=44
    -Wno-unused-variable
    -Wno-unused-function
    -O2
)
