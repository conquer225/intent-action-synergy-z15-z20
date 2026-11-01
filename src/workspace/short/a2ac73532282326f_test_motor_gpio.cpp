#include <cassert>
#include <cstdio>
#include <vector>
#include "../firmware/guardianloop_wheelchair/motor_gpio.h"

static uint32_t outputMask, stuckLowMask;
static int failedPin = -1, configResult;
static std::vector<int> events;
static gpio_config_t configured;

int gpio_set_level(gpio_num_t pin, uint32_t level) {
  events.push_back(pin * 2 + static_cast<int>(level));
  if (pin == failedPin) return -1;
  if (level) outputMask |= UINT32_C(1) << pin;
  else outputMask &= ~(UINT32_C(1) << pin);
  return ESP_OK;
}

int gpio_config(const gpio_config_t *config) {
  events.push_back(-1);configured = *config;return configResult;
}

int gpio_get_level(gpio_num_t pin) {
  return ((outputMask & ~stuckLowMask) >> pin) & 1;
}

static void reset() {
  outputMask = 0x3c00;stuckLowMask = 0;failedPin = -1;configResult = ESP_OK;events.clear();
}

int main() {
  reset();assert(initializeMotorPins());
  assert(configured.pin_bit_mask == 0x3c00);
  assert(configured.mode == GPIO_MODE_INPUT_OUTPUT);
  assert(configured.pull_up_en == GPIO_PULLUP_DISABLE && configured.pull_down_en == GPIO_PULLDOWN_DISABLE);
  assert(configured.intr_type == GPIO_INTR_DISABLE);
  assert(events == std::vector<int>({20,22,24,26,-1,20,22,24,26}));
  assert(outputMask == 0 && readMotorPins() == 0);
  puts("PASS four pins clear before and after explicit input/output configuration");

  for (uint32_t mask : {0u,0x3000u,0x0c00u,0x2400u,0x1800u}) {
    events.clear();assert(applyMotorPins(mask));
    assert(events.size() >= 4 && std::vector<int>(events.begin(),events.begin()+4) == std::vector<int>({20,22,24,26}));
    assert(outputMask == mask && readMotorPins() == mask);
  }
  puts("PASS STOP and all four original output patterns retain exact pin levels");

  assert(applyMotorPins(0x3000));stuckLowMask = 1u << 13;
  assert(readMotorPins() == 0x1000 && outputMask == 0x3000);
  puts("PASS independent input readback exposes a stuck-low pin instead of echoing the request");

  reset();failedPin = 11;assert(!initializeMotorPins());
  assert(events == std::vector<int>({20,22,24,26}));
  events.clear();assert(!applyMotorPins(0x3000));
  assert(events == std::vector<int>({20,22,24,26}));
  reset();configResult = -1;assert(!initializeMotorPins());
  assert(events == std::vector<int>({20,22,24,26,-1}));
  puts("PASS failed clear or configuration never proceeds to high outputs");
  puts("PASS 4 host-only GPIO groups; NO HARDWARE IO");
}
