/*
 * BMI160 G-Force Reader for ESP32-S3
 *
 * Reads acceleration, computes total G-force magnitude, prints it.
 *
 * Wiring:
 *   SCL  -> GPIO6
 *   SDA  -> GPIO5
 *   INT  -> GPIO43
 *   BMI160 I2C address: 0x69
 */

#include <stdio.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#include <bmi160.h>

/* ---------- Pin definitions ---------- */
#define I2C_SCL_GPIO        GPIO_NUM_6
#define I2C_SDA_GPIO        GPIO_NUM_5
#define BMI160_INT_GPIO     GPIO_NUM_43

static const char *TAG = "GFORCE";

static bmi160_t dev = { 0 };

void app_main(void)
{
    esp_err_t ret;

    ESP_ERROR_CHECK(i2cdev_init());

    ret = bmi160_init(&dev, BMI160_I2C_ADDRESS_VDD, I2C_NUM_0, I2C_SDA_GPIO, I2C_SCL_GPIO);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "bmi160_init failed: %s", esp_err_to_name(ret));
        return;
    }

    bmi160_conf_t conf = {
        .accRange = BMI160_ACC_RANGE_16G,
        .accOdr   = BMI160_ACC_ODR_800HZ,
        .accMode  = BMI160_PMU_ACC_NORMAL,
        .accAvg   = BMI160_ACC_LP_AVG_1,
        .accUs    = BMI160_ACC_US_OFF,
        .gyrRange = BMI160_GYR_RANGE_2000DPS,
        .gyrOdr   = BMI160_GYR_ODR_100HZ,
        .gyrMode  = BMI160_PMU_GYR_SUSPEND,
    };

    ret = bmi160_start(&dev, &conf);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "bmi160_start failed: %s", esp_err_to_name(ret));
        return;
    }

    bmi160_int_out_conf_t int_conf = {
        .intPin    = BMI160_PIN_INT1,
        .intEnable = BMI160_INT_ENABLE,
        .intOd     = BMI160_INT_PUSH_PULL,
        .intLevel  = BMI160_INT_ACTIVE_HIGH,
    };
    bmi160_enable_int_new_data(&dev, &int_conf);
    dev.intPin = BMI160_INT_GPIO;

    ESP_LOGI(TAG, "BMI160 ready – ±16g, 800 Hz");

    bmi160_result_t r;
    while (1) {
        if (bmi160_read_data(&dev, &r) == ESP_OK) {
            float total_g = sqrtf(r.accX * r.accX + r.accY * r.accY + r.accZ * r.accZ);
            printf("%.2f G\n", total_g);
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
