#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Used by pq-crystals/dilithium for keypair generation only. */
void randombytes(uint8_t *buf, size_t n);

#ifdef __cplusplus
}
#endif
