#pragma once
#include "Arduino.h"
#include <vector>
#include <deque>
#include <cstring>
constexpr int RF24_1MBPS=0,RF24_PA_LOW=0,RF24_CRC_16=2;
class RF24 {
 public:
 std::deque<std::vector<uint8_t>> packets; std::vector<uint8_t> feedback;
 RF24(int,int) {} bool begin() {return true;}
 void setChannel(int) {} void setDataRate(int) {} void setPALevel(int) {}
 void setCRCLength(int) {} void setAutoAck(bool) {} void enableAckPayload() {}
 void openReadingPipe(int,const uint8_t*) {} void startListening() {}
 bool available() {return !packets.empty();}
 uint8_t getDynamicPayloadSize() {return uint8_t(packets.front().size());}
 void read(void *p,size_t n) {assert(n==packets.front().size()); memcpy(p,packets.front().data(),n);packets.pop_front();}
 void writeAckPayload(int,const void *p,size_t n) {const auto *b=(const uint8_t*)p;feedback.assign(b,b+n);}
 void flush_tx() {} void flush_rx() {packets.clear();}
};
