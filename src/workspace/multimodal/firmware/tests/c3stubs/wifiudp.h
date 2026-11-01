#ifndef TEST_BRIDGE_UDP_H
#define TEST_BRIDGE_UDP_H
#include "WiFi.h"
#include <stdint.h>
#include <stddef.h>
#include <vector>
#include <deque>
#include <algorithm>
#include <string.h>
struct BridgeFakeDatagram {
  uint32_t ip = 0; uint16_t port = 0; std::vector<uint8_t> bytes;
};
class WiFiUDP {
 public:
  inline static std::deque<BridgeFakeDatagram> incoming;
  inline static std::vector<BridgeFakeDatagram> outgoing;
  inline static unsigned begins = 0, stops = 0;
  int begin(uint16_t port) { bound = port; ++begins; return 1; }
  void stop() { bound = 0; active.bytes.clear(); incoming.clear(); ++stops; }
  int parsePacket() {
    if (!active.bytes.empty() || !bound || incoming.empty()) return 0;
    active = incoming.front(); incoming.pop_front(); return int(active.bytes.size());
  }
  IPAddress remoteIP() const { return IPAddress(active.ip); }
  uint16_t remotePort() const { return active.port; }
  int read(uint8_t *buffer, size_t size) {
    size_t count = std::min(size, active.bytes.size()); memcpy(buffer, active.bytes.data(), count);
    active.bytes.erase(active.bytes.begin(), active.bytes.begin() + count); return int(count);
  }
  void flush() { active.bytes.clear(); }
  void clear() { active.bytes.clear(); }
  int beginPacket(IPAddress ip, uint16_t port) { sending = {}; sending.ip = uint32_t(ip); sending.port = port; return 1; }
  size_t write(const uint8_t *bytes, size_t size) { sending.bytes.insert(sending.bytes.end(), bytes, bytes + size); return size; }
  int endPacket() { outgoing.push_back(sending); return 1; }
 private:
  uint16_t bound = 0; BridgeFakeDatagram active, sending;
};
#endif
