#ifndef TEST_BRIDGE_ESP_SYSTEM_H
#define TEST_BRIDGE_ESP_SYSTEM_H
#include <stdint.h>
inline uint32_t esp_random() { static uint32_t sequence = 0x62542203; return ++sequence; }
#endif
