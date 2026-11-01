#ifndef WC_TEST_DRIVER_GPIO_H
#define WC_TEST_DRIVER_GPIO_H

#include <stdint.h>

typedef enum { GPIO_NUM_10=10, GPIO_NUM_11=11, GPIO_NUM_12=12, GPIO_NUM_13=13 } gpio_num_t;
typedef enum { GPIO_MODE_INPUT_OUTPUT=3 } gpio_mode_t;
typedef enum { GPIO_PULLUP_DISABLE=0 } gpio_pullup_t;
typedef enum { GPIO_PULLDOWN_DISABLE=0 } gpio_pulldown_t;
typedef enum { GPIO_INTR_DISABLE=0 } gpio_int_type_t;
typedef struct {
  uint64_t pin_bit_mask;
  gpio_mode_t mode;
  gpio_pullup_t pull_up_en;
  gpio_pulldown_t pull_down_en;
  gpio_int_type_t intr_type;
} gpio_config_t;

#define ESP_OK 0
int gpio_set_level(gpio_num_t pin, uint32_t level);
int gpio_config(const gpio_config_t *config);
int gpio_get_level(gpio_num_t pin);

#endif
