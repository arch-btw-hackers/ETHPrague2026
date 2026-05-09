#ifndef KMS_H
#define KMS_H

#include <esp_err.h>

/**
 * Initialize KMS module.
 * Loads cached key from NVS if available.
 */
esp_err_t kms_init(void);

/**
 * Create an RSA_4096 signing key if not already created.
 * Stores the key ID in NVS for reuse.
 * Returns ESP_OK if key is ready (created or loaded from NVS).
 */
esp_err_t kms_ensure_key(void);

/**
 * Sign a payload string using the RSA_4096 key via Orbitport KMS.
 * The message is sent as RAW (gateway hashes it).
 * Copies the base64 signature into out_sig (up to sig_size chars).
 * Returns ESP_OK on success.
 */
esp_err_t kms_sign(const char *payload, char *out_sig, size_t sig_size);

#endif /* KMS_H */
