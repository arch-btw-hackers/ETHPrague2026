/*
 * ESP32 randombytes shim for PQClean.
 * Must have C linkage — PQClean is compiled as C and calls this symbol directly.
 */
#include "randombytes.h"
#include "esp_random.h"

extern "C" void randombytes(uint8_t *buf, size_t n)
{
    esp_fill_random(buf, n);
}
