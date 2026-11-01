#ifndef TEST_BRIDGE_WIFI_H
#define TEST_BRIDGE_WIFI_H
#include <stdint.h>
constexpr int WL_CONNECTED = 3;
class IPAddress {
 public:
  IPAddress(uint32_t raw = 0) : value(raw) {}
  IPAddress(uint8_t a, uint8_t b, uint8_t c, uint8_t d) : value(uint32_t(a) | (uint32_t(b)<<8) | (uint32_t(c)<<16) | (uint32_t(d)<<24)) {}
  operator uint32_t() const { return value; }
  uint8_t operator[](unsigned index) const { return uint8_t(value >> (index * 8)); }
  uint8_t &operator[](unsigned index) { return reinterpret_cast<uint8_t *>(&value)[index]; }
 private:
  uint32_t value;
};
struct BridgeFakeWiFi {
  int state = WL_CONNECTED;
  int status() const { return state; }
  IPAddress localIP() const { return IPAddress(10,0,0,20); }
  IPAddress subnetMask() const { return IPAddress(255,255,255,0); }
};
inline BridgeFakeWiFi WiFi;
#endif
