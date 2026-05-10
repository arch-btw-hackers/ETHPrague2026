#ifndef BEACON_H
#define BEACON_H

#include <esp_err.h>

/**
 * Fetch cosmic entropy from the public beacon.
 * Copies the hex nonce string into `out_buf` (up to `buf_size` chars).
 * Returns ESP_OK on success.
 */
esp_err_t beacon_fetch_entropy(char *out_buf, size_t buf_size);

#endif /* BEACON_H */
