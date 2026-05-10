#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* PQCP libraries (mlkem-native, mldsa-native) expect int randombytes().
 * Returns 0 on success, non-zero on failure. */
int randombytes(uint8_t *buf, size_t n);

#ifdef __cplusplus
}
#endif
