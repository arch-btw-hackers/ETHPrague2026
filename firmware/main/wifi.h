#ifndef WIFI_H
#define WIFI_H

#include <esp_err.h>

/**
 * Initialize WiFi in STA mode and connect.
 * Blocks until connected or fails after timeout.
 * Returns ESP_OK on successful connection.
 */
esp_err_t wifi_init_sta(void);

#endif /* WIFI_H */
