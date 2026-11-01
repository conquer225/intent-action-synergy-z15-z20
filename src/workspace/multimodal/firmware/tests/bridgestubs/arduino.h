#ifndef TEST_BRIDGE_ARDUINO_H
#define TEST_BRIDGE_ARDUINO_H
#include <stdint.h>
#include <stddef.h>
extern uint32_t bridgeFakeMillis;
inline uint32_t millis() { return bridgeFakeMillis; }
#endif
