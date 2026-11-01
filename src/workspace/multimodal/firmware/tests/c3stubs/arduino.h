#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cstdio>
#include <deque>
#include <vector>
inline uint32_t fakeMillis = 0;
inline uint32_t millis() { return fakeMillis; }
inline void delay(unsigned ms) { fakeMillis += ms; }
constexpr uint32_t SERIAL_8N1 = 0;
class HardwareSerial {
 public:
  uint32_t baud = 0; int rx = -1, tx = -1, freeBytes = 1024;
  unsigned blockedWrites = 0;
  std::deque<uint8_t> input; std::vector<uint8_t> output;
  void begin(uint32_t speed, uint32_t = SERIAL_8N1, int receive = -1, int transmit = -1) { baud = speed; rx = receive; tx = transmit; }
  void setDebugOutput(bool) {}
  void setRxBufferSize(size_t) {}
  void setTxBufferSize(size_t) {}
  int available() { return int(input.size()); }
  int read() { auto b = input.front(); input.pop_front(); return b; }
  int availableForWrite() { return freeBytes; }
  size_t write(const uint8_t* b, size_t n) { if (freeBytes < int(n)) ++blockedWrites; output.insert(output.end(), b, b+n); return n; }
};
inline HardwareSerial Serial, Serial1;
inline uint32_t esp_random() { return 0xaabbccdd; }
struct FakeESP { uint32_t random() { return esp_random(); } };
inline FakeESP ESP;
