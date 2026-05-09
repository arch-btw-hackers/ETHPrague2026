#include "pqc.h"

#include "mbedtls/gcm.h"
#include "mbedtls/sha256.h"
#include "mbedtls/hkdf.h"
#include "mbedtls/md.h"
#include "mbedtls/platform_util.h"

#include "nvs_flash.h"
#include "nvs.h"
#include "esp_random.h"
#include "esp_log.h"

#include <cstring>
#include <cassert>

/*
 * ML-KEM-512  — pq-code-package/mlkem-native  (MLK_CONFIG_PARAMETER_SET=512)
 * ML-DSA-44   — pq-code-package/mldsa-native  (MLD_CONFIG_PARAMETER_SET=44)
 *
 * Both libraries are compiled as C — forward-declare their symbols here with
 * C linkage.  Clangd will show a "definition not found" hint until the
 * submodules are cloned (make submodule-mlkem / make submodule-mldsa), but
 * this does not prevent compilation.
 *
 * ML-KEM encapsulation coin size (FIPS 203 §6.2): 32 bytes.
 * ML-DSA-44 signature (FIPS 204): ctx/ctxlen added vs. Dilithium2; pass NULL, 0.
 */
extern "C" {
    int mlkem512_enc_derand(
        uint8_t       *ct,
        uint8_t       *ss,
        const uint8_t *pk,
        const uint8_t *coins);   /* 32 bytes of fresh randomness */

    int mldsa44_keypair(uint8_t *pk, uint8_t *sk);
    int mldsa44_signature(
        uint8_t       *sig, size_t *siglen,
        const uint8_t *m,   size_t  mlen,
        const uint8_t *ctx, size_t  ctxlen,  /* FIPS 204 context: pass NULL, 0 */
        const uint8_t *sk);
}

static const char *TAG = "pqc";

static constexpr char    NVS_NS[]            = "pqc";
static constexpr char    NVS_KEY_DSA_SK[]    = "dsa_sk";
static constexpr char    NVS_KEY_DSA_PK[]    = "dsa_pk";
static constexpr char    NVS_KEY_KEM_PK_BE[] = "kem_pk_be";
static constexpr uint8_t HKDF_INFO[]         = "cold-chain-v1";

/* Size of the randomness passed to mlkem512_enc_derand (FIPS 203 §6.2) */
static constexpr size_t MLKEM512_ENC_COINS = 32;

/* ── Internal helpers ────────────────────────────────────────────────────── */

static esp_err_t nvs_open_rw(nvs_handle_t &h)
{
    esp_err_t err = nvs_open(NVS_NS, NVS_READWRITE, &h);
    if (err != ESP_OK)
        ESP_LOGE(TAG, "nvs_open failed: %s", esp_err_to_name(err));
    return err;
}

static esp_err_t nvs_open_ro(nvs_handle_t &h)
{
    esp_err_t err = nvs_open(NVS_NS, NVS_READONLY, &h);
    if (err != ESP_OK)
        ESP_LOGE(TAG, "nvs_open (ro) failed: %s", esp_err_to_name(err));
    return err;
}

static esp_err_t derive_session_key(const uint8_t *ss, uint8_t *key_out)
{
    int rc = mbedtls_hkdf(
        mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),
        nullptr, 0,
        ss, PQC_KEM_SS_BYTES,
        HKDF_INFO, sizeof(HKDF_INFO) - 1,
        key_out, PQC_SESSION_KEY_BYTES
    );
    if (rc != 0) {
        ESP_LOGE(TAG, "HKDF failed: -0x%04x", static_cast<unsigned>(-rc));
        return ESP_FAIL;
    }
    return ESP_OK;
}

/* ── Public API ──────────────────────────────────────────────────────────── */

esp_err_t pqc_init(pqc_context_t *ctx)
{
    assert(ctx != nullptr);
    std::memset(ctx, 0, sizeof(*ctx));
    return pqc_load_keys(ctx);
}

esp_err_t pqc_generate_keys(pqc_context_t *ctx)
{
    assert(ctx != nullptr);

    ESP_LOGI(TAG, "Generating ML-DSA-44 keypair...");

    /*
     * crypto_sign_keypair calls randombytes() internally for the 32-byte seed.
     * Our ESP32 shim in components/mldsa/ wires that to esp_fill_random().
     */
    if (mldsa44_keypair(ctx->dsa_pk_device, ctx->dsa_sk_device) != 0) {
        ESP_LOGE(TAG, "ML-DSA keypair generation failed");
        return ESP_FAIL;
    }

    nvs_handle_t h;
    esp_err_t err = nvs_open_rw(h);
    if (err != ESP_OK) return err;

    err = nvs_set_blob(h, NVS_KEY_DSA_SK, ctx->dsa_sk_device, PQC_DSA_SK_BYTES);
    if (err == ESP_OK)
        err = nvs_set_blob(h, NVS_KEY_DSA_PK, ctx->dsa_pk_device, PQC_DSA_PK_BYTES);
    if (err == ESP_OK)
        err = nvs_commit(h);

    nvs_close(h);

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS write failed: %s", esp_err_to_name(err));
        return err;
    }

    ESP_LOGI(TAG, "Keys generated and stored in NVS");
    return ESP_OK;
}

esp_err_t pqc_load_keys(pqc_context_t *ctx)
{
    assert(ctx != nullptr);

    nvs_handle_t h;
    esp_err_t err = nvs_open_ro(h);
    if (err != ESP_OK) return err;

    size_t sz_sk  = PQC_DSA_SK_BYTES;
    size_t sz_pk  = PQC_DSA_PK_BYTES;
    size_t sz_kem = PQC_KEM_PK_BYTES;

    err = nvs_get_blob(h, NVS_KEY_DSA_SK,    ctx->dsa_sk_device,  &sz_sk);
    if (err == ESP_OK)
        err = nvs_get_blob(h, NVS_KEY_DSA_PK, ctx->dsa_pk_device,  &sz_pk);
    if (err == ESP_OK)
        err = nvs_get_blob(h, NVS_KEY_KEM_PK_BE, ctx->kem_pk_backend, &sz_kem);

    nvs_close(h);

    if (err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "Keys not found in NVS — device needs provisioning");
        return ESP_ERR_NVS_NOT_FOUND;
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS read failed: %s", esp_err_to_name(err));
    }
    return err;
}

esp_err_t pqc_establish_session(pqc_context_t *ctx)
{
    assert(ctx != nullptr);

    /*
     * Use the deterministic (_derand) encapsulation variant.
     * We supply the 32-byte randomness directly from ESP32 hardware RNG
     * rather than letting the library call an internal randombytes() shim.
     * This makes the entropy source explicit and lets us zeroize the coins.
     */
    uint8_t coins        [MLKEM512_ENC_COINS];
    uint8_t shared_secret[PQC_KEM_SS_BYTES];

    esp_fill_random(coins, sizeof(coins));

    int rc = mlkem512_enc_derand(
        ctx->kem_ct, shared_secret, ctx->kem_pk_backend, coins);

    mbedtls_platform_zeroize(coins, sizeof(coins));

    if (rc != 0) {
        ESP_LOGE(TAG, "ML-KEM encapsulation failed");
        mbedtls_platform_zeroize(shared_secret, sizeof(shared_secret));
        return ESP_FAIL;
    }

    esp_err_t err = derive_session_key(shared_secret, ctx->session_key);
    mbedtls_platform_zeroize(shared_secret, sizeof(shared_secret));

    if (err != ESP_OK) return err;

    ESP_LOGI(TAG, "Session established (ML-KEM-512 encaps + HKDF)");
    return ESP_OK;
}

esp_err_t pqc_encrypt_telemetry(
    const pqc_context_t *ctx,
    const uint8_t *aad,    size_t aad_len,
    const uint8_t *pt,     size_t pt_len,
    uint8_t       *nonce_out,
    uint8_t       *ct_out,
    uint8_t       *tag_out)
{
    assert(ctx && aad && pt && nonce_out && ct_out && tag_out);

    esp_fill_random(nonce_out, PQC_NONCE_BYTES);

    mbedtls_gcm_context gcm;
    mbedtls_gcm_init(&gcm);

    int rc = mbedtls_gcm_setkey(&gcm, MBEDTLS_CIPHER_ID_AES,
                                  ctx->session_key, PQC_SESSION_KEY_BYTES * 8);
    if (rc != 0) {
        ESP_LOGE(TAG, "GCM setkey: -0x%04x", static_cast<unsigned>(-rc));
        mbedtls_gcm_free(&gcm);
        return ESP_FAIL;
    }

    rc = mbedtls_gcm_crypt_and_tag(
        &gcm, MBEDTLS_GCM_ENCRYPT,
        pt_len,
        nonce_out, PQC_NONCE_BYTES,
        aad, aad_len,
        pt, ct_out,
        PQC_TAG_BYTES, tag_out
    );

    mbedtls_gcm_free(&gcm);

    if (rc != 0) {
        ESP_LOGE(TAG, "GCM encrypt: -0x%04x", static_cast<unsigned>(-rc));
        return ESP_FAIL;
    }

    return ESP_OK;
}

esp_err_t pqc_sign_batch(
    pqc_context_t *ctx,
    const uint8_t *batch, size_t batch_len)
{
    assert(ctx && batch && batch_len > 0);

    uint8_t hash[32];
    if (mbedtls_sha256(batch, batch_len, hash, 0) != 0) {
        ESP_LOGE(TAG, "SHA-256 failed");
        return ESP_FAIL;
    }

    /*
     * crypto_sign_signature from pq-crystals/dilithium is deterministic
     * (no randombytes() call during signing — nonce derived internally via SHAKE).
     * Stack peak: ~7.5 KB — task stack must be ≥ 12 KB.
     */
    ctx->sig_len = PQC_DSA_SIG_BYTES;
    if (mldsa44_signature(
            ctx->signature, &ctx->sig_len,
            hash, sizeof(hash),
            nullptr, 0,
            ctx->dsa_sk_device) != 0) {
        ESP_LOGE(TAG, "ML-DSA sign failed");
        mbedtls_platform_zeroize(hash, sizeof(hash));
        return ESP_FAIL;
    }

    mbedtls_platform_zeroize(hash, sizeof(hash));
    ESP_LOGI(TAG, "Batch signed: %zu bytes", ctx->sig_len);
    return ESP_OK;
}

void pqc_zeroize(pqc_context_t *ctx)
{
    if (ctx == nullptr) return;
    mbedtls_platform_zeroize(ctx->dsa_sk_device,
        PQC_DSA_SK_BYTES + PQC_SESSION_KEY_BYTES);
}
