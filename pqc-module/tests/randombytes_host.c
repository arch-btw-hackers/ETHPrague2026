#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

/* PQCP libraries expect: int randombytes(uint8_t *out, size_t outlen) */

#if defined(__APPLE__) || defined(__FreeBSD__) || defined(__OpenBSD__)
#  include <stdlib.h>
int randombytes(uint8_t *buf, size_t n) {
    arc4random_buf(buf, n);
    return 0;
}
#elif defined(__linux__)
#  include <sys/random.h>
int randombytes(uint8_t *buf, size_t n) {
    ssize_t r = getrandom(buf, n, 0);
    if (r < 0 || (size_t)r != n) { perror("getrandom"); return -1; }
    return 0;
}
#else
int randombytes(uint8_t *buf, size_t n) {
    FILE *f = fopen("/dev/urandom", "rb");
    if (!f || fread(buf, 1, n, f) != n) { perror("/dev/urandom"); return -1; }
    fclose(f);
    return 0;
}
#endif
