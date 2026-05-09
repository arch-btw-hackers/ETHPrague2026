#include "client.h"
#include <string.h>
#include "esp_log.h"
#include "esp_http_client.h"
#include "esp_random.h"
#include "mbedtls/pk.h"
#include "mbedtls/base64.h"

static const char *TAG = "CLIENT";

// The local IP of the mock server
#define SERVER_IP "192.168.11.152"
#define PUBKEY_URL "http://" SERVER_IP ":3000/pubkey"
#define INGEST_URL "http://" SERVER_IP ":3000/ingest"

static char s_server_pubkey[2048] = {0};

static int my_random(void *p_rng, unsigned char *output, size_t output_len) {
    esp_fill_random(output, output_len);
    return 0;
}

esp_err_t client_fetch_pubkey(void) {
    ESP_LOGI(TAG, "Fetching server public key from %s", PUBKEY_URL);
    esp_http_client_config_t config = {
        .url = PUBKEY_URL,
        .method = HTTP_METHOD_GET,
        .timeout_ms = 5000,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) return ESP_FAIL;

    esp_err_t err = esp_http_client_open(client, 0);
    if (err == ESP_OK) {
        esp_http_client_fetch_headers(client);
        int len = esp_http_client_read(client, s_server_pubkey, sizeof(s_server_pubkey) - 1);
        if (len > 0) {
            s_server_pubkey[len] = '\0';
            ESP_LOGI(TAG, "Fetched Server Pubkey (len=%d)", len);
        } else {
            ESP_LOGE(TAG, "Failed to read server pubkey response");
            err = ESP_FAIL;
        }
    } else {
        ESP_LOGE(TAG, "Failed to connect to %s", PUBKEY_URL);
    }
    esp_http_client_cleanup(client);
    return err;
}

esp_err_t client_send_encrypted(const char *payload) {
    if (strlen(s_server_pubkey) == 0) {
        ESP_LOGE(TAG, "No server pubkey to encrypt with");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Encrypting payload (%d bytes)...", (int)strlen(payload));

    mbedtls_pk_context pk;
    mbedtls_pk_init(&pk);
    
    // Parse public key
    int ret = mbedtls_pk_parse_public_key(&pk, (const unsigned char *)s_server_pubkey, strlen(s_server_pubkey) + 1);
    if (ret != 0) {
        ESP_LOGE(TAG, "Failed to parse pubkey: -0x%04x", -ret);
        mbedtls_pk_free(&pk);
        return ESP_FAIL;
    }

    // Encrypt payload (RSA PKCS1 v1.5)
    unsigned char enc_buf[512] = {0};
    size_t enc_len = 0;
    ret = mbedtls_pk_encrypt(&pk, (const unsigned char *)payload, strlen(payload),
                             enc_buf, &enc_len, sizeof(enc_buf),
                             my_random, NULL);
    mbedtls_pk_free(&pk);

    if (ret != 0) {
        ESP_LOGE(TAG, "Failed to encrypt: -0x%04x", -ret);
        return ESP_FAIL;
    }

    // Base64 encode
    unsigned char b64_buf[1024] = {0};
    size_t b64_len = 0;
    mbedtls_base64_encode(b64_buf, sizeof(b64_buf), &b64_len, enc_buf, enc_len);

    // Create JSON for ingest
    char post_data[1200];
    snprintf(post_data, sizeof(post_data), "{\"encrypted_payload\":\"%s\"}", b64_buf);

    ESP_LOGI(TAG, "Sending POST to %s...", INGEST_URL);

    // Send POST
    esp_http_client_config_t config = {
        .url = INGEST_URL,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 5000,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, post_data, strlen(post_data));
    
    esp_err_t err = esp_http_client_perform(client);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "✅ Successfully sent encrypted payload to server! Status = %d", esp_http_client_get_status_code(client));
    } else {
        ESP_LOGE(TAG, "Failed to send encrypted payload: %s", esp_err_to_name(err));
    }
    
    esp_http_client_cleanup(client);
    return err;
}
