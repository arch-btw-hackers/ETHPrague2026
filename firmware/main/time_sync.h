#ifndef TIME_SYNC_H
#define TIME_SYNC_H

#include <esp_err.h>

/**
 * Initialize SNTP and wait until the system time is synchronized.
 * Must be called after WiFi is connected.
 */
esp_err_t time_sync_init(void);

#endif /* TIME_SYNC_H */
