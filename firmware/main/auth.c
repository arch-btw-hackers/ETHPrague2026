                /*
 * OAuth2 Client Credentials auth for Orbitport
 *
 * POST https://auth.spacecomputer.io/oauth/token
 * Body: {"client_id":"...","client_secret":"...","audience":"https://op.spacecomputer.io/api","grant_type":"client_credentials"}
 * Response: {"access_token":"<JWT>","expires_in":86400,"token_type":"Bearer"}
 *
 * Token is cached in NVS. JWT exp claim is checked before reuse.
 */

#include "auth.h"

#include <string.h>
#include <time.h>
#include "esp_log.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "cJSON.h"
#include "mbedtls/base64.h"

static const char *TAG = "AUTH";

#define AUTH_URL         "https://auth.spacecomputer.io/oauth/token"
#define AUTH_AUDIENCE    "https://op.spacecomputer.io/api"
#define NVS_NAMESPACE    "orbitport"
#define NVS_TOKEN_KEY    "jwt_token"
#define TOKEN_BUF_SIZE   4096
#define EXPIRY_BUFFER_S  60   /* Refresh 60s before actual expiry */

/* ------------------------------------------------------------------ */
/*  JWT expiry check                                                    */
/* ------------------------------------------------------------------ */

/**
 * Decode JWT payload (middle part) and extract "exp" claim.
 * Returns the exp timestamp, or 0 on failure.
 */
static time_t jwt_get_exp(const char *jwt)
{
    /* Find the payload section (between first and second dot) */
    const char *dot1 = strchr(jwt, '.');
    if (!dot1) return 0;
    const char *payload_start = dot1 + 1;
    const char *dot2 = strchr(payload_start, '.');
    if (!dot2) return 0;

    size_t b64_len = dot2 - payload_start;
    if (b64_len > 2048) return 0;

    /* Base64url -> base64 (replace - with +, _ with /) */
    char b64[2048];
    memcpy(b64, payload_start, b64_len);
    b64[b64_len] = '\0';
    for (int i = 0; i < (int)b64_len; i++) {
        if (b64[i] == '-') b64[i] = '+';
        else if (b64[i] == '_') b64[i] = '/';
    }
    /* Pad to multiple of 4 */
    while (b64_len % 4 != 0) {
        b64[b64_len++] = '=';
        b64[b64_len] = '\0';
    }

    /* Decode */
    unsigned char decoded[2048];
    size_t decoded_len = 0;
    int ret = mbedtls_base64_decode(decoded, sizeof(decoded) - 1,
                                     &decoded_len,
                                     (const unsigned char *)b64, b64_len);
    if (ret != 0) return 0;
    decoded[decoded_len] = '\0';

    /* Parse JSON for "exp" */
    cJSON *root = cJSON_Parse((const char *)decoded);
    if (!root) return 0;
    cJSON *exp = cJSON_GetObjectItem(root, "exp");
    time_t exp_val = 0;
    if (exp && cJSON_IsNumber(exp)) {
        exp_val = (time_t)exp->valuedouble;
    }
    cJSON_Delete(root);
    return exp_val;
}

static bool jwt_is_expired(const char *jwt)
{
    time_t exp = jwt_get_exp(jwt);
    if (exp == 0) return true;  /* Can't parse → treat as expired */

    time_t now;
    time(&now);
    /* If system time is not set (< year 2020), we can't check expiry */
    if (now < 1577836800) {
        ESP_LOGW(TAG, "System time not set, assuming token valid");
        return false;
    }
    return now >= (exp - EXPIRY_BUFFER_S);
}

/* ------------------------------------------------------------------ */
/*  NVS helpers                                                         */
/* ------------------------------------------------------------------ */

static esp_err_t nvs_load_token(char *out, size_t out_size)
{
    nvs_handle_t h;
    esp_err_t ret = nvs_open(NVS_NAMESPACE, NVS_READONLY, &h);
    if (ret != ESP_OK) return ret;

    size_t len = out_size;
    ret = nvs_get_str(h, NVS_TOKEN_KEY, out, &len);
    nvs_close(h);
    return ret;
}

static esp_err_t nvs_save_token(const char *token)
{
    nvs_handle_t h;
    esp_err_t ret = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h);
    if (ret != ESP_OK) return ret;

    ret = nvs_set_str(h, NVS_TOKEN_KEY, token);
    if (ret == ESP_OK) {
        nvs_commit(h);
    }
    nvs_close(h);
    return ret;
}

/* ------------------------------------------------------------------ */
/*  HTTP token fetch                                                    */
/* ------------------------------------------------------------------ */

static int s_http_output_len = 0;

static esp_err_t http_event_handler(esp_http_client_event_t *evt)
{
    switch (evt->event_id) {
    case HTTP_EVENT_ON_DATA:
        if (evt->user_data) {
            int copy_len = evt->data_len;
            if (s_http_output_len + copy_len >= TOKEN_BUF_SIZE) {
                copy_len = TOKEN_BUF_SIZE - s_http_output_len - 1;
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

static esp_err_t fetch_new_token(char *out_token, size_t token_size)
{
    char *response_buf = calloc(1, TOKEN_BUF_SIZE);
    if (!response_buf) return ESP_ERR_NO_MEM;

    s_http_output_len = 0;

    esp_http_client_config_t config = {
        .url = AUTH_URL,
        .method = HTTP_METHOD_POST,
        .event_handler = http_event_handler,
        .user_data = response_buf,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .timeout_ms = 30000,
        .buffer_size = 2048,
        .buffer_size_tx = 2048,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        free(response_buf);
        return ESP_FAIL;
    }

    /* Build request body */
    cJSON *body = cJSON_CreateObject();
    cJSON_AddStringToObject(body, "client_id", USER_ID);
    cJSON_AddStringToObject(body, "client_secret", SECRET);
    cJSON_AddStringToObject(body, "audience", AUTH_AUDIENCE);
    cJSON_AddStringToObject(body, "grant_type", "client_credentials");
    char *body_str = cJSON_PrintUnformatted(body);
    cJSON_Delete(body);

    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, body_str, strlen(body_str));

    ESP_LOGI(TAG, "Requesting token from %s", AUTH_URL);
    esp_err_t err = esp_http_client_perform(client);

    if (err == ESP_OK) {
        int status = esp_http_client_get_status_code(client);
        ESP_LOGI(TAG, "Auth response status: %d", status);

        if (status == 200 && strlen(response_buf) > 0) {
            cJSON *resp = cJSON_Parse(response_buf);
            if (resp) {
                cJSON *access_token = cJSON_GetObjectItem(resp, "access_token");
                if (access_token && access_token->valuestring) {
                    strncpy(out_token, access_token->valuestring, token_size - 1);
                    out_token[token_size - 1] = '\0';

                    /* Save to NVS */
                    nvs_save_token(out_token);

                    time_t exp = jwt_get_exp(out_token);
                    ESP_LOGI(TAG, "Token obtained (exp=%lld, len=%d)",
                             (long long)exp, (int)strlen(out_token));
                } else {
                    ESP_LOGE(TAG, "No access_token in response");
                    err = ESP_FAIL;
                }
                cJSON_Delete(resp);
            } else {
                ESP_LOGE(TAG, "Failed to parse auth response");
                err = ESP_FAIL;
            }
        } else {
            ESP_LOGE(TAG, "Auth failed: status=%d body=%.200s", status, response_buf);
            err = ESP_FAIL;
        }
    } else {
        ESP_LOGE(TAG, "Auth HTTP request failed: %s", esp_err_to_name(err));
    }

    free(body_str);
    esp_http_client_cleanup(client);
    free(response_buf);
    return (strlen(out_token) > 0) ? ESP_OK : ESP_FAIL;
}

/* ------------------------------------------------------------------ */
/*  Public API                                                          */
/* ------------------------------------------------------------------ */

esp_err_t auth_init(void)
{
    ESP_LOGI(TAG, "Auth module initialized");
    return ESP_OK;
}

esp_err_t auth_get_token(char *out_token, size_t token_size)
{
    if (!out_token || token_size == 0) return ESP_ERR_INVALID_ARG;
    out_token[0] = '\0';

    /* Try loading cached token from NVS */
    char *cached = calloc(1, TOKEN_BUF_SIZE);
    if (!cached) return ESP_ERR_NO_MEM;

    if (nvs_load_token(cached, TOKEN_BUF_SIZE) == ESP_OK && strlen(cached) > 0) {
        if (!jwt_is_expired(cached)) {
            ESP_LOGI(TAG, "Using cached token from NVS (not expired)");
            strncpy(out_token, cached, token_size - 1);
            out_token[token_size - 1] = '\0';
            free(cached);
            return ESP_OK;
        }
        ESP_LOGI(TAG, "Cached token expired, fetching new one");
    } else {
        ESP_LOGI(TAG, "No cached token, fetching new one");
    }
    free(cached);

    /* Fetch new token */
    return fetch_new_token(out_token, token_size);
}
