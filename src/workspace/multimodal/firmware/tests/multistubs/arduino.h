#pragma once
#include <stdint.h>
#include <stddef.h>
#include <cstdio>
#include <cstdarg>
#include <string>
#include <sstream>
#include <deque>
#include <vector>
#define ARDUINO_USB_CDC_ON_BOOT 1
inline uint64_t fakeUs = 0;
inline bool fakeWorn = true;
inline int fakeEmgAmplitude = 40;
inline unsigned fakeEmgReads = 0;
inline uint16_t fakePots[6] = {3000,3000,3000,3000,3000,1000};
constexpr int HIGH=1, LOW=0, INPUT=0, OUTPUT=1, ADC_11db=3, SERIAL_8N1=0;
inline unsigned fakePwm[49]={};
inline unsigned fakePinWrites[49]={};
inline int fakePinModes[49]={};
inline bool fakePwmAttached[49]={};
inline uint16_t fakeProbe3=1234, fakeProbe8=2345;
inline void digitalWrite(int pin,int value) { ++fakePinWrites[pin]; fakePwm[pin]=value; }
inline bool ledcAttachChannel(int pin,unsigned,int,int) { fakePwmAttached[pin]=true; return true; }
inline bool ledcDetach(int pin) { fakePwmAttached[pin]=false; return true; }
inline bool ledcWrite(int pin,unsigned duty) { ++fakePinWrites[pin]; fakePwm[pin]=duty; return true; }
constexpr float RAD_TO_DEG = 57.2957795f, DEG_TO_RAD = 0.0174532925f;
inline uint32_t micros() { return (uint32_t)fakeUs; }
inline uint32_t millis() { return (uint32_t)(fakeUs / 1000); }
inline void delay(unsigned ms) { fakeUs += 1000ULL * ms; }
inline void pinMode(int pin, int mode) { fakePinModes[pin]=mode; }
inline void analogReadResolution(int) {}
inline void analogSetPinAttenuation(int, int) {}
inline int digitalRead(int) { return fakeWorn ? 1 : 0; }
inline int analogRead(int pin) {
  if (pin==3) return fakeProbe3;
  if (pin==8) return fakeProbe8;
  if (pin == 1) return 2000 + ((++fakeEmgReads & 1) ? fakeEmgAmplitude : -fakeEmgAmplitude);
  constexpr int pins[6]={4,5,6,7,9,10};
  for(int i=0;i<6;++i) if(pin==pins[i]) return fakePots[i];
  return 0;
}
class HardwareSerial {
 public:
  explicit HardwareSerial(int = 0) {}
  std::string output;
  std::vector<uint8_t> wire;
  std::deque<char> input;
  int txFree=2048;
  uint32_t txTimeoutMs=100;
  unsigned stalledWrites=0;
  void setTxBufferSize(size_t) {}
  void setTxTimeoutMs(uint32_t timeout) { txTimeoutMs=timeout; }
  int availableForWrite() { return txFree; }
  void begin(unsigned, int = 0, int = -1, int = -1) {}
  int available() { return (int)input.size(); }
  int read() { if (input.empty()) return -1; char c = input.front(); input.pop_front(); return c; }
  void feed(const char *s) { while (*s) input.push_back(*s++); }
  size_t write(const uint8_t *p, size_t n) { wire.insert(wire.end(), p, p+n); return n; }
  void emit(const std::string &text) {
    if (txFree<int(text.size())) {
      if (txTimeoutMs) { ++stalledWrites; fakeUs+=20000ULL*txTimeoutMs; }
      return;
    }
    output+=text;
  }
  template<class T> void print(T value) { std::ostringstream s; s << value; emit(s.str()); }
  template<class T> void println(T value) { print(value); emit("\n"); }
  void println() { emit("\n"); }
  void printf(const char *fmt, ...) {
    char text[1024]; va_list args; va_start(args, fmt);
    vsnprintf(text, sizeof(text), fmt, args); va_end(args); emit(text);
  }
};
inline HardwareSerial Serial;
