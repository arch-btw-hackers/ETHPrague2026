#pragma once
#include "esp_err.h"

/**
 * Fetch the server's RSA public key from GET /api/v1/auth/keys.
 * Call once on startup; the key is stored in RAM for subsequent encryptions.
 */
esp_err_t client_fetch_pubkey(void);

/**
 * Encrypt readings_json with the server RSA key (OAEP/SHA-256),
 * and write the base64 ciphertext into out_ct_b64.
 */
esp_err_t client_encrypt(const char *readings_json,
                          char *out_ct_b64, size_t ct_b64_size);

/**
 * POST the final packet to /api/v1/sensors/encrypted-data.
 * Body: { device_id, nonce, ciphertext, signature }
 */
esp_err_t client_post(const char *device_id,
                       const char *nonce,
                       const char *ciphertext_b64,
                       const char *signature);
