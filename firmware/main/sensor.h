#ifndef SENSOR_H
#define SENSOR_H

#include <esp_err.h>

/**
 * Initialize BMI160 sensor over I2C.
 */
esp_err_t sensor_init(void);

/**
 * Read total G-force magnitude (√(x²+y²+z²)).
 * Returns -1.0f on error.
 */
float sensor_read_g(void);

/**
 * Read temperature from BMI160 in °C.
 * Returns -999.0f on error.
 */
float sensor_read_temp(void);

/**
 * Get the peak G recorded since last reset.
 */
float sensor_get_peak_g(void);

/**
 * Reset the peak G tracker.
 */
void sensor_reset_peak_g(void);

#endif /* SENSOR_H */
