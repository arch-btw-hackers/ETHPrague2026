/*
 * Cosmic entropy beacon fetcher
 *
 * Fetches random data from the public IPFS beacon.
 * Retries up to 3 times with increasing timeout.
 */

#include "beacon.h"

#include <string.h>
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_crt_bundle.h"
#include "cJSON.h"

static const char *TAG = "BEACON";

#define BEACON_URL "https://ipfs.io/ipns/k2k4r8lvomw737sajfnpav0dpeernugnryng50uheyk1k39lursmn09f"
#define RESPONSE_BUF_SIZE 2048
#define MAX_RETRIES 3

/* HTTP event handler to capture response body */
static int s_output_len = 0;

static esp_err_t http_event_handler(esp_http_client_event_t *evt)
{
    switch (evt->event_id) {
    case HTTP_EVENT_ON_DATA:
        if (evt->user_data) {
            int copy_len = evt->data_len;
            if (s_output_len + copy_len >= RESPONSE_BUF_SIZE) {
                copy_len = RESPONSE_BUF_SIZE - s_output_len - 1;
            }
            if (copy_len > 0) {
                memcpy((char *)evt->user_data + s_output_len, evt->data, copy_len);
                s_output_len += copy_len;
                ((char *)evt->user_data)[s_output_len] = '\0';
            }
        }
        break;
    case HTTP_EVENT_ON_FINISH:
    case HTTP_EVENT_DISCONNECTED:
        s_output_len = 0;
        break;
    default:
        break;
    }
    return ESP_OK;
}

static esp_err_t try_fetch(char *out_buf, size_t buf_size, int timeout_ms)
{
    char *response_buf = calloc(1, RESPONSE_BUF_SIZE);
    if (!response_buf) return ESP_ERR_NO_MEM;

    s_output_len = 0;

    esp_http_client_config_t config = {
        .url = BEACON_URL,
        .method = HTTP_METHOD_GET,
        .event_handler = http_event_handler,
        .user_data = response_buf,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .timeout_ms = timeout_ms,
        .buffer_size = 1024,
        .buffer_size_tx = 512,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        free(response_buf);
        return ESP_FAIL;
    }

    esp_err_t err = esp_http_client_perform(client);

    if (err == ESP_OK) {
        int status = esp_http_client_get_status_code(client);
        if (status == 200 && strlen(response_buf) > 0) {
            cJSON *root = cJSON_Parse(response_buf);
            if (root) {
                cJSON *data = cJSON_GetObjectItem(root, "data");
                if (data) {
                    cJSON *ctrng_array = cJSON_GetObjectItem(data, "ctrng");
                    if (ctrng_array && cJSON_IsArray(ctrng_array)) {
                        cJSON *first_val = cJSON_GetArrayItem(ctrng_array, 0);
                        if (first_val && first_val->valuestring) {
                            strncpy(out_buf, first_val->valuestring, buf_size - 1);
                            out_buf[buf_size - 1] = '\0';
                        }
                    }
                }
                cJSON_Delete(root);
            } else {
                err = ESP_FAIL;
            }
        } else {
            err = ESP_FAIL;
        }
    }

    esp_http_client_cleanup(client);
    free(response_buf);
    return (strlen(out_buf) > 0) ? ESP_OK : ESP_FAIL;
}

esp_err_t beacon_fetch_entropy(char *out_buf, size_t buf_size)
{
    if (!out_buf || buf_size == 0) return ESP_ERR_INVALID_ARG;
    out_buf[0] = '\0';

    for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
        int timeout = 30000 + (attempt * 15000);  /* 30s, 45s, 60s */
        ESP_LOGI(TAG, "Fetching entropy (attempt %d/%d, timeout %ds)...",
                 attempt + 1, MAX_RETRIES, timeout / 1000);

        esp_err_t err = try_fetch(out_buf, buf_size, timeout);
        if (err == ESP_OK) {
            ESP_LOGI(TAG, "Got entropy: %.32s...", out_buf);
            return ESP_OK;
        }

        ESP_LOGW(TAG, "Attempt %d failed, %s",
                 attempt + 1,
                 (attempt < MAX_RETRIES - 1) ? "retrying..." : "giving up");
    }

    return ESP_FAIL;
}
