#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

/* macOS / BSDs: arc4random_buf is always available and uses the kernel CSPRNG */
#if defined(__APPLE__) || defined(__FreeBSD__) || defined(__OpenBSD__)
#  include <stdlib.h>
void randombytes(uint8_t *buf, size_t n) {
    arc4random_buf(buf, n);
}
/* Linux: getrandom(2) — never blocks after boot */
#elif defined(__linux__)
#  include <sys/random.h>
void randombytes(uint8_t *buf, size_t n) {
    ssize_t r = getrandom(buf, n, 0);
    if (r < 0 || (size_t)r != n) { perror("getrandom"); abort(); }
}
/* Fallback */
#else
#  include <stdio.h>
void randombytes(uint8_t *buf, size_t n) {
    FILE *f = fopen("/dev/urandom", "rb");
    if (!f || fread(buf, 1, n, f) != n) { perror("/dev/urandom"); abort(); }
    fclose(f);
}
#endif
