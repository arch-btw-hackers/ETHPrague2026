#ifndef AUTH_H
#define AUTH_H

#include <esp_err.h>

/**
 * Initialize auth module (loads cached token from NVS).
 */
esp_err_t auth_init(void);

/**
 * Get a valid Bearer token.
 * Returns cached token from NVS if not expired,
 * otherwise fetches a new one from auth.spacecomputer.io.
 * Copies the token into out_token (up to token_size chars).
 * Returns ESP_OK on success.
 */
esp_err_t auth_get_token(char *out_token, size_t token_size);

#endif /* AUTH_H */
