/*
 * randombytes() shim for PQCP libraries (mlkem-native, mldsa-native).
 * Called during randomized keypair generation; signing is deterministic.
 * Must have C linkage because PQCP libs are compiled as C.
 */
#include "randombytes.h"
#include "esp_random.h"

extern "C" int randombytes(uint8_t *buf, size_t n)
{
    esp_fill_random(buf, n);
    return 0;
}
