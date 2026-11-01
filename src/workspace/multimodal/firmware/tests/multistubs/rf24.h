#pragma once
#include "Arduino.h"
#include "SPI.h"
#include <cstring>
constexpr int RF24_1MBPS=0, RF24_PA_LOW=0, RF24_CRC_16=2;
inline bool fakeRfPresent = true, fakeRfFailure = false;
inline unsigned fakeRfWrites = 0;
inline uint16_t fakePressures[5]={1000,1000,1000,1000,1000};
inline uint8_t fakeRfFlags=0x20;
inline int fakeFeedbackSequence=-1;
inline int16_t fakeSentAngles[6]={};
inline std::vector<std::vector<uint8_t>> fakeRfPackets;
class RF24 {
 public:
  RF24(int, int, unsigned long) {}
  bool begin(SPIClass*) { pending=ack=false; return fakeRfPresent; }
  void setChannel(int) {} void setDataRate(int) {} void setPALevel(int) {}
  void setCRCLength(int) {} void setRetries(int,int) {} void setAutoAck(bool) {}
  void enableAckPayload() {} void openWritingPipe(const uint8_t*) {} void stopListening() {}
  void flush_tx() { pending=false; } void flush_rx() { ack=false; }
  bool startWrite(const void *p, uint8_t n, bool) {
    if (pending || n!=14) return false;
    ++fakeRfWrites; pending=true; started=fakeUs;
    const uint8_t *b=(const uint8_t*)p; seq=(uint16_t)b[0]|((uint16_t)b[1]<<8);
    for(int i=0;i<6;++i) fakeSentAngles[i]=b[2+2*i]|(b[3+2*i]<<8);
    fakeRfPackets.emplace_back(b,b+n);
    return true;
  }
  void whatHappened(bool &ok, bool &failed, bool &received) {
    ok=failed=received=false;
    if (!pending || fakeUs-started < (fakeRfFailure ? 60000ULL : 1000ULL)) return;
    pending=false;
    if (fakeRfFailure) { failed=true; return; }
    ok=received=ack=true;
  }
  bool available() { return ack; }
  uint8_t getDynamicPayloadSize() { return ack ? 13 : 0; }
  void read(void *p, size_t n) {
    uint16_t feedbackSeq=fakeFeedbackSequence>=0 ? (uint16_t)fakeFeedbackSequence : (uint16_t)(seq-1);
    uint8_t b[13]={(uint8_t)feedbackSeq,(uint8_t)(feedbackSeq>>8)};
    for(int i=0;i<5;++i) { b[2+2*i]=(uint8_t)fakePressures[i]; b[3+2*i]=(uint8_t)(fakePressures[i]>>8); }
    b[12]=fakeRfFlags;
    if(n==13) memcpy(p,b,13); ack=false;
  }
 private:
  bool pending=false, ack=false;
  uint64_t started=0;
  uint16_t seq=0;
};
