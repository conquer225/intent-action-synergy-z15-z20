#pragma once
#include <cstdint>
#include <string>
constexpr int WL_CONNECTED = 3, WIFI_OFF = 0, WIFI_STA = 1, WIFI_AP = 2;
class IPAddress {
 public:
  explicit IPAddress(uint32_t value = 0) : ip(value) {}
  IPAddress(uint8_t a, uint8_t b, uint8_t c, uint8_t d) : ip(a | uint32_t(b)<<8 | uint32_t(c)<<16 | uint32_t(d)<<24) {}
  operator uint32_t() const { return ip; }
 private: uint32_t ip;
};
struct C3FakeWiFi {
  int radio = WIFI_OFF; bool apResult = true; unsigned apCalls = 0;
  std::string ssid, password;
  int status() { return 0; } // SoftAP has no station connection.
  bool mode(int m) { radio=m; return true; }
  int getMode() { return radio; }
  void setSleep(bool) {}
  void setHostname(const char*) {}
  void begin(const char*, const char*) {}
  bool softAPConfig(IPAddress, IPAddress, IPAddress) { return true; }
  bool softAP(const char* s, const char* p, int channel, bool hidden, int clients) {
    ssid=s; password=p; ++apCalls; return apResult && channel==6 && !hidden && clients==4;
  }
  unsigned softAPgetStationNum() { return 1; }
};
inline C3FakeWiFi WiFi;
