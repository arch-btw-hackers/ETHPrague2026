/*
 * BMI160 sensor module
 *
 * Wiring:
 *   SCL  -> GPIO6
 *   SDA  -> GPIO5
 *   INT  -> GPIO43
 *   BMI160 I2C address: 0x69
 */

#include "sensor.h"

#include <math.h>
#include "esp_log.h"
#include <bmi160.h>
#include <bmi160_reg.h>

#define I2C_SCL_GPIO    GPIO_NUM_6
#define I2C_SDA_GPIO    GPIO_NUM_5
#define BMI160_INT_GPIO GPIO_NUM_43

static const char *TAG = "SENSOR";
static bmi160_t dev = { 0 };
static float peak_g = 0.0f;

esp_err_t sensor_init(void)
{
    esp_err_t ret;

    ESP_ERROR_CHECK(i2cdev_init());

    ret = bmi160_init(&dev, BMI160_I2C_ADDRESS_VDD, I2C_NUM_0, I2C_SDA_GPIO, I2C_SCL_GPIO);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "bmi160_init failed: %s", esp_err_to_name(ret));
        return ret;
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
        return ret;
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
    return ESP_OK;
}

float sensor_read_g(void)
{
    bmi160_result_t r;
    if (bmi160_read_data(&dev, &r) != ESP_OK) {
        return -1.0f;
    }
    float g = sqrtf(r.accX * r.accX + r.accY * r.accY + r.accZ * r.accZ);

    /* Track peak */
    if (g > peak_g) {
        peak_g = g;
    }
    return g;
}

float sensor_read_temp(void)
{
    uint8_t buf[2];
    esp_err_t ret;

    /* Read temperature registers 0x20 (LSB) and 0x21 (MSB) */
    ret = bmi160_read_reg(&dev, BMI160_TEMPERATURE_0, &buf[0]);
    if (ret != ESP_OK) return -999.0f;
    ret = bmi160_read_reg(&dev, BMI160_TEMPERATURE_1, &buf[1]);
    if (ret != ESP_OK) return -999.0f;

    int16_t raw = (int16_t)((buf[1] << 8) | buf[0]);

    /* BMI160 datasheet: temp_degC = raw / 512.0 + 23.0
     * 0x0000 = 23°C, resolution = 1/512 °C/LSB */
    float temp_c = (raw / 512.0f) + 23.0f;
    return temp_c;
}

float sensor_get_peak_g(void)
{
    return peak_g;
}

void sensor_reset_peak_g(void)
{
    peak_g = 0.0f;
}
