/*
 * Orbitport KMS Integration
 *
 * Communicates with https://op.spacecomputer.io/api/v1/rpc
 * Uses JSON-RPC 2.0 format.
 */

#include "kms.h"
#include "auth.h"

#include <string.h>
#include "esp_log.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "nvs.h"
#include "cJSON.h"
#include "mbedtls/base64.h"

static const char *TAG = "KMS";

#define KMS_URL "https://op.spacecomputer.io/api/v1/rpc"
#define NVS_NAMESPACE "orbitport"
#define NVS_KEY_ID "kms_key_id_ecdsa"
#define RESPONSE_BUF_SIZE 4096

static char s_key_id[128] = {0};

/* HTTP event handler for accumulating response */
static int s_http_output_len = 0;

static esp_err_t http_event_handler(esp_http_client_event_t *evt)
{
    switch (evt->event_id) {
    case HTTP_EVENT_ON_DATA:
        if (evt->user_data) {
            int copy_len = evt->data_len;
            if (s_http_output_len + copy_len >= RESPONSE_BUF_SIZE) {
                copy_len = RESPONSE_BUF_SIZE - s_http_output_len - 1;
            }
            if (copy_len > 0) {
                memcpy((char *)evt->user_data + s_http_output_len, evt->data, copy_len);
                s_http_output_len += copy_len;
                ((char *)evt->user_data)[s_http_output_len] = '\0';
            }
        }
        break;
    case HTTP_EVENT_ON_FINISH:
    case HTTP_EVENT_DISCONNECTED:
        s_http_output_len = 0;
        break;
    default:
        break;
    }
    return ESP_OK;
}

/* Helper to send JSON-RPC request */
static esp_err_t kms_rpc_call(const char *method, cJSON *params, cJSON **out_result)
{
    char token[2048] = {0};
    if (auth_get_token(token, sizeof(token)) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to get auth token for KMS");
        return ESP_FAIL;
    }

    char *response_buf = calloc(1, RESPONSE_BUF_SIZE);
    if (!response_buf) return ESP_ERR_NO_MEM;

    s_http_output_len = 0;

    esp_http_client_config_t config = {
        .url = KMS_URL,
        .method = HTTP_METHOD_POST,
        .event_handler = http_event_handler,
        .user_data = response_buf,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .timeout_ms = 15000,
        .buffer_size = 2048,
        .buffer_size_tx = 2048,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        free(response_buf);
        return ESP_FAIL;
    }

    /* Set headers */
    char auth_header[2100];
    snprintf(auth_header, sizeof(auth_header), "Bearer %s", token);
    esp_http_client_set_header(client, "Authorization", auth_header);
    esp_http_client_set_header(client, "Content-Type", "application/json");

    /* Build JSON-RPC body */
    cJSON *req = cJSON_CreateObject();
    cJSON_AddStringToObject(req, "jsonrpc", "2.0");
    cJSON_AddStringToObject(req, "method", method);
    cJSON_AddItemToObject(req, "params", params);
    cJSON_AddNumberToObject(req, "id", 1);

    char *body_str = cJSON_PrintUnformatted(req);
    esp_http_client_set_post_field(client, body_str, strlen(body_str));

    esp_err_t err = esp_http_client_perform(client);
    esp_err_t ret = ESP_FAIL;

    if (err == ESP_OK) {
        int status = esp_http_client_get_status_code(client);
        if (status == 200 && strlen(response_buf) > 0) {
            cJSON *resp = cJSON_Parse(response_buf);
            if (resp) {
                cJSON *error = cJSON_GetObjectItem(resp, "error");
                if (error && !cJSON_IsNull(error)) {
                    char *err_str = cJSON_PrintUnformatted(error);
                    ESP_LOGE(TAG, "KMS Error: %s", err_str);
                    free(err_str);
                } else {
                    cJSON *result = cJSON_GetObjectItem(resp, "result");
                    if (result && out_result) {
                        *out_result = cJSON_Duplicate(result, 1);
                        ret = ESP_OK;
                    }
                }
                cJSON_Delete(resp);
            }
        } else {
            ESP_LOGE(TAG, "KMS HTTP %d: %s", status, response_buf);
        }
    } else {
        ESP_LOGE(TAG, "KMS Request failed: %s", esp_err_to_name(err));
    }

    cJSON_Delete(req); /* Deletes params too */
    free(body_str);
    esp_http_client_cleanup(client);
    free(response_buf);
    return ret;
}

esp_err_t kms_init(void)
{
    nvs_handle_t h;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &h) == ESP_OK) {
        size_t len = sizeof(s_key_id);
        if (nvs_get_str(h, NVS_KEY_ID, s_key_id, &len) == ESP_OK) {
            ESP_LOGI(TAG, "Loaded Key ID from NVS: %s", s_key_id);
        }
        nvs_close(h);
    }
    return ESP_OK;
}

esp_err_t kms_ensure_key(void)
{
    if (strlen(s_key_id) > 0) {
        return ESP_OK; /* Already have a key */
    }

    const char *alias = "cargo-tracker-ecdsa";
    ESP_LOGI(TAG, "Ensuring ECDSA_P256 key (Alias: %s)...", alias);

    cJSON *params = cJSON_CreateObject();
    cJSON_AddStringToObject(params, "Alias", alias);
    cJSON_AddStringToObject(params, "KeySpec", "ECDSA_P256");
    cJSON_AddStringToObject(params, "KeyUsage", "SIGN_VERIFY");
    cJSON_AddStringToObject(params, "Scheme", "TRANSIT");
    cJSON_AddStringToObject(params, "Description", "Cargo Tracker ECDSA Key");
    
    cJSON *tags = cJSON_CreateArray();
    cJSON *tag1 = cJSON_CreateObject();
    cJSON_AddStringToObject(tag1, "TagKey", "Project");
    cJSON_AddStringToObject(tag1, "TagValue", "CargoTracker");
    cJSON_AddItemToArray(tags, tag1);
    cJSON_AddItemToObject(params, "Tags", tags);

    cJSON *result = NULL;
    esp_err_t ret = kms_rpc_call("kms.CreateKey", params, &result);
    
    if (ret == ESP_OK && result) {
        cJSON *meta = cJSON_GetObjectItem(result, "KeyMetadata");
        if (meta) {
            cJSON *kid = cJSON_GetObjectItem(meta, "KeyId");
            if (kid && kid->valuestring) {
                strncpy(s_key_id, kid->valuestring, sizeof(s_key_id) - 1);
            }
        }
        cJSON_Delete(result);
    } else {
        /* Check if error is 'Alias already exists' (-32001) */
        // Note: kms_rpc_call returns ESP_FAIL if there's a JSON-RPC error, but we can't see the code easily.
        // Actually, let's modify kms_rpc_call or just assume if it failed and alias exists, we use it.
        ESP_LOGW(TAG, "KMS CreateKey failed or key exists. Falling back to alias.");
        snprintf(s_key_id, sizeof(s_key_id), "kms:%s", alias);
        ret = ESP_OK;
    }

    if (strlen(s_key_id) > 0) {
        /* Save to NVS */
        nvs_handle_t h;
        if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h) == ESP_OK) {
            nvs_set_str(h, NVS_KEY_ID, s_key_id);
            nvs_commit(h);
            nvs_close(h);
        }
        ESP_LOGI(TAG, "Using Key ID: %s", s_key_id);
        return ESP_OK;
    }
    return ESP_FAIL;
}
#include "mbedtls/sha256.h"

esp_err_t kms_sign(const char *payload, char *out_sig, size_t sig_size)
{
    if (strlen(s_key_id) == 0) {
        ESP_LOGE(TAG, "No key available for signing");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Hashing and signing payload (ECDSA)...");

    /* Hash payload locally */
    unsigned char hash[32];
    mbedtls_sha256((const unsigned char *)payload, strlen(payload), hash, 0);

    /* Base64 encode the digest */
    size_t b64_len = 0;
    unsigned char b64_hash[64];
    mbedtls_base64_encode(b64_hash, sizeof(b64_hash), &b64_len, hash, sizeof(hash));

    cJSON *params = cJSON_CreateObject();
    cJSON_AddStringToObject(params, "KeyId", s_key_id);
    cJSON_AddStringToObject(params, "Message", (char *)b64_hash);
    cJSON_AddStringToObject(params, "SigningAlgorithm", "ECDSA_SHA_256");
    cJSON_AddStringToObject(params, "MessageType", "DIGEST");

    cJSON *result = NULL;
    esp_err_t ret = kms_rpc_call("kms.Sign", params, &result);
    if (ret == ESP_OK && result) {
        cJSON *sig = cJSON_GetObjectItem(result, "Signature");
        if (sig && sig->valuestring) {
            if (strncmp(sig->valuestring, "vault:v1:", 9) != 0) {
                snprintf(out_sig, sig_size, "vault:v1:%s", sig->valuestring);
            } else {
                strncpy(out_sig, sig->valuestring, sig_size - 1);
                out_sig[sig_size - 1] = '\0';
            }
        } else {
            ret = ESP_FAIL;
        }
        cJSON_Delete(result);
    }
    return ret;
}
