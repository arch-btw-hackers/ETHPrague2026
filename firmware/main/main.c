/*
 * Main – ESP32-S3 Cargo Shock Tracker
 *
 * On boot + every minute:
 *   1. Authenticate with Orbitport (OAuth2 JWT, cached in NVS)
 *   2. Fetch cosmic entropy nonce from beacon
 *   3. Read peak G-force from the last interval
 *   4. Read temperature from BMI160
 *   5. Print JSON report
 *
 * Between reports, continuously samples G-force and tracks the peak.
 */

#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "sensor.h"
#include "wifi.h"
#include "beacon.h"
#include "auth.h"
#include "kms.h"
#include "time_sync.h"
#include "client.h"

static const char *TAG = "MAIN";

#define DEVICE_ID       "cargo_tracker_9000"
#define REPORT_INTERVAL_MS  60000   /* 1 minute */
#define SAMPLE_INTERVAL_MS  20      /* 50 Hz sampling */

static char s_token[2048] = {0};

static void print_report(void)
{
    char nonce[128] = {0};

    /* Ensure we have a valid token */
    if (auth_get_token(s_token, sizeof(s_token)) == ESP_OK) {
        ESP_LOGI(TAG, "Token ready (len=%d)", (int)strlen(s_token));
    } else {
        ESP_LOGW(TAG, "No valid token available");
    }

    /* Get peak G and reset for next interval */
    float peak = sensor_get_peak_g();
    sensor_reset_peak_g();

    /* Read temperature from BMI160 */
    float temp = sensor_read_temp();

    /* Fetch cosmic entropy */
    if (beacon_fetch_entropy(nonce, sizeof(nonce)) != ESP_OK) {
        strncpy(nonce, "fetch-failed", sizeof(nonce) - 1);
    }

    /* Step 2: Build readings JSON (only sensor data) */
    char readings[256];
    snprintf(readings, sizeof(readings),
        "{\"temp_c\":%.1f,\"acceleration_overload\":%.3f}",
        temp, peak);

    /* Step 3: Encrypt readings with server RSA key (OAEP SHA-256) */
    char ciphertext[512] = {0};
    if (client_encrypt(readings, ciphertext, sizeof(ciphertext)) != ESP_OK) {
        ESP_LOGE(TAG, "Encryption failed, skipping report");
        return;
    }

    /* Step 4: Sign  nonce + device_id + ciphertext  via KMS (ECDSA P-256) */
    char sign_input[1024];
    snprintf(sign_input, sizeof(sign_input), "%s%s%s", nonce, DEVICE_ID, ciphertext);

    char signature[512] = {0};
    if (kms_sign(sign_input, signature, sizeof(signature)) != ESP_OK) {
        strncpy(signature, "signing-failed", sizeof(signature) - 1);
    }

    /* Print for debug */
    printf("{\n");
    printf("  \"device_id\": \"%s\",\n", DEVICE_ID);
    printf("  \"nonce\": \"%s\",\n", nonce);
    printf("  \"ciphertext\": \"%s\",\n", ciphertext);
    printf("  \"signature\": \"%s\"\n", signature);
    printf("}\n");

    ESP_LOGI(TAG, "Report: peak=%.3fG temp=%.1f°C", peak, temp);

    /* Step 5: POST to server */
    client_post(DEVICE_ID, nonce, ciphertext, signature);
}

/* Sampling task — runs continuously, silently feeds peak tracker */
static void sensor_task(void *arg)
{
    while (1) {
        sensor_read_g();  /* Internally tracks peak */
        vTaskDelay(pdMS_TO_TICKS(SAMPLE_INTERVAL_MS));
    }
}

/* Report task — first report immediately, then every minute */
static void report_task(void *arg)
{
    /* First report right away */
    print_report();

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(REPORT_INTERVAL_MS));
        print_report();
    }
}

void app_main(void)
{
    /* 1. Init sensor */
    client_led_init();
    if (sensor_init() != ESP_OK) {
        ESP_LOGE(TAG, "Sensor init failed");
        return;
    }

    /* 2. Connect WiFi */
    if (wifi_init_sta() != ESP_OK) {
        ESP_LOGE(TAG, "WiFi failed");
        return;
    }

    /* 2.5 Sync time via SNTP (required for JWT expiry check) */
    time_sync_init();

    /* 3. Init auth module */
    auth_init();

    /* 4. Test auth — get token right away */
    if (auth_get_token(s_token, sizeof(s_token)) == ESP_OK) {
        ESP_LOGI(TAG, "Auth OK – token length: %d", (int)strlen(s_token));
    } else {
        ESP_LOGE(TAG, "Auth FAILED – continuing without signing");
    }

    /* 4.5 Initialize KMS and ensure we have an RSA key */
    kms_init();
    if (kms_ensure_key() == ESP_OK) {
        ESP_LOGI(TAG, "KMS Key ready");
    } else {
        ESP_LOGE(TAG, "Failed to get/create KMS key");
    }

    /* 4.6 Fetch Server Public Key */
    if (client_fetch_pubkey() != ESP_OK) {
        ESP_LOGE(TAG, "Failed to fetch server public key, encryption will fail.");
    }

    /* 5. Start sampling task – pinned to core 1 (WiFi on core 0) */
    xTaskCreatePinnedToCore(sensor_task, "sensor", 4096, NULL, 3, NULL, 1);

    /* 6. Start reporting task */
    xTaskCreate(report_task, "report", 24576, NULL, 5, NULL);

    ESP_LOGI(TAG, "System running – reports every %d seconds", REPORT_INTERVAL_MS / 1000);
}
