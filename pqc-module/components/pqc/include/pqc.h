#pragma once

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ── ML-KEM-512 (FIPS 203) ──────────────────────────────────────────────── */
#define PQC_KEM_PK_BYTES  800
#define PQC_KEM_CT_BYTES  768
#define PQC_KEM_SS_BYTES  32

/* ── ML-DSA-44 (FIPS 204) ───────────────────────────────────────────────── */
#define PQC_DSA_PK_BYTES  1312
#define PQC_DSA_SK_BYTES  2560
#define PQC_DSA_SIG_BYTES 2420

/* ── AES-256-GCM ────────────────────────────────────────────────────────── */
#define PQC_SESSION_KEY_BYTES 32
#define PQC_NONCE_BYTES       12
#define PQC_TAG_BYTES         16

/* ── Telemetry batch limits ─────────────────────────────────────────────── */
#define PQC_BATCH_JSON_MAX  4096   /* max serialized batch size in bytes */

/*
 * All secret material lives inside pqc_context_t.  Allocate it as a static
 * variable in the PQC task — never on a shared heap.
 *
 * Field layout is intentional: secrets are contiguous at the top so that
 * pqc_zeroize() can be implemented as a single mbedtls_platform_zeroize call
 * on the struct up to the non-secret boundary.
 */
typedef struct {
    /* ── Secrets (zeroize on exit) ─────────────────────────────────────── */
    uint8_t dsa_sk_device [PQC_DSA_SK_BYTES];    /* ML-DSA-44 signing key  */
    uint8_t session_key   [PQC_SESSION_KEY_BYTES];/* ephemeral, per-upload  */

    /* ── Non-secrets ────────────────────────────────────────────────────── */
    uint8_t kem_pk_backend[PQC_KEM_PK_BYTES];    /* backend KEM public key */
    uint8_t dsa_pk_device [PQC_DSA_PK_BYTES];    /* our DSA public key     */
    uint8_t kem_ct        [PQC_KEM_CT_BYTES];    /* KEM ciphertext → backend*/
    uint8_t signature     [PQC_DSA_SIG_BYTES];   /* batch signature output  */
    size_t  sig_len;
} pqc_context_t;

/*
 * pqc_init — initialize RNG (call after Wi-Fi start) and load keys from NVS.
 * Returns ESP_ERR_NVS_NOT_FOUND if keys have never been provisioned;
 * call pqc_generate_keys() in that case.
 */
esp_err_t pqc_init(pqc_context_t *ctx);

/*
 * pqc_generate_keys — generate a fresh ML-DSA-44 keypair and persist to NVS.
 * Call once during device provisioning.
 */
esp_err_t pqc_generate_keys(pqc_context_t *ctx);

/*
 * pqc_load_keys — load previously generated keys from NVS into ctx.
 */
esp_err_t pqc_load_keys(pqc_context_t *ctx);

/*
 * pqc_establish_session — encapsulate to backend KEM public key.
 * Fills ctx->kem_ct (send this to backend) and ctx->session_key (keep secret).
 * Call pqc_zeroize() after the upload session is complete.
 */
esp_err_t pqc_establish_session(pqc_context_t *ctx);

/*
 * pqc_encrypt_telemetry — AES-256-GCM encrypt a telemetry batch.
 *
 *   aad/aad_len  — additional authenticated data (not encrypted, e.g. routing header)
 *   pt/pt_len    — plaintext batch JSON
 *   nonce_out    — caller-allocated PQC_NONCE_BYTES buffer (filled with random)
 *   ct_out       — caller-allocated ≥ pt_len bytes buffer
 *   tag_out      — caller-allocated PQC_TAG_BYTES buffer
 */
esp_err_t pqc_encrypt_telemetry(
    const pqc_context_t *ctx,
    const uint8_t *aad,    size_t aad_len,
    const uint8_t *pt,     size_t pt_len,
    uint8_t       *nonce_out,
    uint8_t       *ct_out,
    uint8_t       *tag_out
);

/*
 * pqc_sign_batch — SHA-256 hash the batch then ML-DSA-44 sign the hash.
 * Fills ctx->signature and ctx->sig_len.
 */
esp_err_t pqc_sign_batch(
    pqc_context_t *ctx,
    const uint8_t *batch, size_t batch_len
);

/*
 * pqc_zeroize — securely wipe all secret material (dsa_sk, session_key).
 * Call after each upload session.
 */
void pqc_zeroize(pqc_context_t *ctx);

#ifdef __cplusplus
}
#endif
