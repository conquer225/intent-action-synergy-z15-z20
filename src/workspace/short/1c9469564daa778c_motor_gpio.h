#ifndef WC_MOTOR_GPIO_H
#define WC_MOTOR_GPIO_H

#include <stdint.h>
#include <driver/gpio.h>

static const gpio_num_t motorPins[] = {GPIO_NUM_10, GPIO_NUM_11, GPIO_NUM_12, GPIO_NUM_13};

static bool clearMotorPins() {
  bool ok = true;
  for (gpio_num_t pin : motorPins) if (gpio_set_level(pin, 0) != ESP_OK) ok = false;
  return ok;
}

static bool initializeMotorPins() {
  if (!clearMotorPins()) return false;
  gpio_config_t config = {};
  for (gpio_num_t pin : motorPins) config.pin_bit_mask |= UINT64_C(1) << pin;
  config.mode = GPIO_MODE_INPUT_OUTPUT;
  config.pull_up_en = GPIO_PULLUP_DISABLE;
  config.pull_down_en = GPIO_PULLDOWN_DISABLE;
  config.intr_type = GPIO_INTR_DISABLE;
  if (gpio_config(&config) != ESP_OK) return false;
  return clearMotorPins();
}

static bool applyMotorPins(uint32_t mask) {
  if (!clearMotorPins()) return false;
  for (gpio_num_t pin : motorPins) {
    if ((mask & (UINT32_C(1) << pin)) && gpio_set_level(pin, 1) != ESP_OK) return false;
  }
  return true;
}

static uint32_t readMotorPins() {
  uint32_t mask = 0;
  for (gpio_num_t pin : motorPins) if (gpio_get_level(pin)) mask |= UINT32_C(1) << pin;
  return mask;
}

#endif
