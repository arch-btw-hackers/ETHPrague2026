#pragma once
#include "esp_err.h"

esp_err_t client_fetch_pubkey(void);
esp_err_t client_send_encrypted(const char *payload);
