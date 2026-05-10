#include "client.h"
#include <string.h>
#include "esp_log.h"
#include "esp_http_client.h"
#include "esp_random.h"
#include "cJSON.h"
#include <oqs/oqs.h>
#include "mbedtls/gcm.h"
#include "mbedtls/base64.h"

#include "mbedtls/entropy.h"
#include "driver/gpio.h"

static const char *TAG = "CLIENT";

#define STATUS_LED_GPIO GPIO_NUM_21  /* Change this to your board's LED pin */

#define SERVER_HOST "http://80.211.207.162:8000"
#define PUBKEY_URL  SERVER_HOST "/api/v1/auth/keys"
#define INGEST_URL  SERVER_HOST "/api/v1/sensors/encrypted-data"

static char s_server_pubkey[2048] = {0};

/* Hardware RNG for mbedtls */
static int hw_random(void *p_rng, unsigned char *output, size_t output_len)
{
    (void)p_rng;
    esp_fill_random(output, output_len);
    return 0;
}

void client_led_init(void)
{
    gpio_reset_pin(STATUS_LED_GPIO);
    gpio_set_direction(STATUS_LED_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(STATUS_LED_GPIO, 1); /* Start OFF for inverted LED */
}

void client_led_blink(void)
{
    gpio_set_level(STATUS_LED_GPIO, 0); /* ON (Active Low) */
    vTaskDelay(pdMS_TO_TICKS(100));
    gpio_set_level(STATUS_LED_GPIO, 1); /* OFF */
}

/* ------------------------------------------------------------------ */
/* 1. GET /api/v1/auth/keys  →  store PEM in RAM                     */
/* ------------------------------------------------------------------ */
esp_err_t client_fetch_pubkey(void)
{
    ESP_LOGI(TAG, "Fetching server public key from %s", PUBKEY_URL);

    char resp_buf[2048] = {0};

    esp_http_client_config_t config = {
        .url         = PUBKEY_URL,
        .method      = HTTP_METHOD_GET,
        .timeout_ms  = 10000,
        .buffer_size = 2048,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) return ESP_FAIL;

    esp_err_t err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Connect failed: %s", esp_err_to_name(err));
        esp_http_client_cleanup(client);
        return ESP_FAIL;
    }

    esp_http_client_fetch_headers(client);
    int len = esp_http_client_read(client, resp_buf, sizeof(resp_buf) - 1);
    esp_http_client_cleanup(client);

    if (len <= 0) {
        ESP_LOGE(TAG, "Empty response from key server");
        return ESP_FAIL;
    }
    resp_buf[len] = '\0';

    /* Parse: {"public_key":"-----BEGIN PUBLIC KEY-----\n..."} */
    cJSON *root = cJSON_Parse(resp_buf);
    if (!root) {
        ESP_LOGE(TAG, "JSON parse failed. Body: %s", resp_buf);
        return ESP_FAIL;
    }
    
    /* Check for 'public_key' or 'server_public_key' */
    cJSON *pk = cJSON_GetObjectItem(root, "public_key");
    if (!pk) {
        pk = cJSON_GetObjectItem(root, "server_public_key");
    }

    if (!pk || !pk->valuestring) {
        ESP_LOGE(TAG, "No public_key field in response. Full body: %s", resp_buf);
        cJSON_Delete(root);
        return ESP_FAIL;
    }
    strncpy(s_server_pubkey, pk->valuestring, sizeof(s_server_pubkey) - 1);
    cJSON_Delete(root);

    ESP_LOGI(TAG, "Server RSA pubkey ready (len=%d)", (int)strlen(s_server_pubkey));
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
/* 2. RSA-OAEP SHA-256 encrypt → base64                              */
/* ------------------------------------------------------------------ */
esp_err_t client_encrypt(const char *plaintext,
                          char *out_b64, size_t b64_size)
{
    if (strlen(s_server_pubkey) == 0) {
        ESP_LOGE(TAG, "No server pubkey");
        return ESP_FAIL;
    }

    OQS_KEM *kem = OQS_KEM_new(OQS_KEM_alg_kyber_768);
    if (!kem) {
        ESP_LOGE(TAG, "Failed to init Kyber-768");
        return ESP_FAIL;
    }

    size_t pk_len = 0;
    unsigned char *public_key = malloc(kem->length_public_key);
    mbedtls_base64_decode(public_key, kem->length_public_key, &pk_len, 
                          (const unsigned char*)s_server_pubkey, strlen(s_server_pubkey));
    if (pk_len != kem->length_public_key) {
        ESP_LOGE(TAG, "Invalid Kyber PK length: expected %d, got %d", (int)kem->length_public_key, (int)pk_len);
        free(public_key);
        OQS_KEM_free(kem);
        return ESP_FAIL;
    }

    unsigned char *kyber_ct = malloc(kem->length_ciphertext);
    unsigned char *shared_secret = malloc(kem->length_shared_secret);

    if (OQS_KEM_encaps(kem, kyber_ct, shared_secret, public_key) != OQS_SUCCESS) {
        ESP_LOGE(TAG, "Kyber encaps failed");
        free(public_key); free(kyber_ct); free(shared_secret); OQS_KEM_free(kem);
        return ESP_FAIL;
    }

    unsigned char iv[12];
    hw_random(NULL, iv, sizeof(iv));

    unsigned char tag[16];
    size_t pt_len = strlen(plaintext);
    unsigned char *aes_ct = malloc(pt_len);

    mbedtls_gcm_context gcm;
    mbedtls_gcm_init(&gcm);
    mbedtls_gcm_setkey(&gcm, MBEDTLS_CIPHER_ID_AES, shared_secret, 256);

    mbedtls_gcm_crypt_and_tag(&gcm, MBEDTLS_GCM_ENCRYPT, pt_len,
                              iv, sizeof(iv), NULL, 0,
                              (const unsigned char*)plaintext, aes_ct, sizeof(tag), tag);
    mbedtls_gcm_free(&gcm);

    size_t packed_len = kem->length_ciphertext + sizeof(iv) + sizeof(tag) + pt_len;
    unsigned char *packed = malloc(packed_len);
    
    size_t offset = 0;
    memcpy(packed + offset, kyber_ct, kem->length_ciphertext); offset += kem->length_ciphertext;
    memcpy(packed + offset, iv, sizeof(iv)); offset += sizeof(iv);
    memcpy(packed + offset, tag, sizeof(tag)); offset += sizeof(tag);
    memcpy(packed + offset, aes_ct, pt_len);

    size_t final_b64_len = 0;
    mbedtls_base64_encode((unsigned char*)out_b64, b64_size, &final_b64_len, packed, packed_len);

    free(public_key); free(kyber_ct); free(shared_secret); free(aes_ct); free(packed);
    OQS_KEM_free(kem);

    ESP_LOGI(TAG, "Encrypted payload (Kyber768 + AES-GCM) ready, length: %d", (int)final_b64_len);
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
/* 3. POST /api/v1/sensors/encrypted-data                            */
/* ------------------------------------------------------------------ */
esp_err_t client_post(const char *device_id,
                       const char *nonce,
                       const char *ciphertext_b64,
                       const char *signature)
{
    cJSON *body = cJSON_CreateObject();
    cJSON_AddStringToObject(body, "device_id",  device_id);
    cJSON_AddStringToObject(body, "nonce",      nonce);
    cJSON_AddStringToObject(body, "ciphertext", ciphertext_b64);
    cJSON_AddStringToObject(body, "signature",  signature);

    char *json_str = cJSON_PrintUnformatted(body);
    cJSON_Delete(body);
    if (!json_str) return ESP_FAIL;

    ESP_LOGI(TAG, "POST %s (%d bytes)", INGEST_URL, (int)strlen(json_str));

    esp_http_client_config_t config = {
        .url         = INGEST_URL,
        .method      = HTTP_METHOD_POST,
        .timeout_ms  = 10000,
        .buffer_size = 2048,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, json_str, strlen(json_str));

    esp_err_t err = esp_http_client_perform(client);
    if (err == ESP_OK) {
        int status = esp_http_client_get_status_code(client);
        ESP_LOGI(TAG, "Server responded HTTP %d", status);
        
        /* Print response body */
        char resp_buf[512] = {0};
        int read_len = esp_http_client_read(client, resp_buf, sizeof(resp_buf) - 1);
        if (read_len > 0) {
            resp_buf[read_len] = '\0';
            ESP_LOGI(TAG, "Response Body: %s", resp_buf);
        }

        if (status == 200) {
            client_led_blink();
        }
    } else {
        ESP_LOGE(TAG, "POST failed: %s", esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    cJSON_free(json_str);
    return err;
}
