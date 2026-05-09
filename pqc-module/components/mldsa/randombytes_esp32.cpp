/*
 * randombytes() shim for pq-crystals/dilithium.
 * Called only during keypair generation — signing is deterministic.
 * Must have C linkage because dilithium is compiled as C.
 */
#include "randombytes.h"
#include "esp_random.h"

extern "C" void randombytes(uint8_t *buf, size_t n)
{
    esp_fill_random(buf, n);
}
