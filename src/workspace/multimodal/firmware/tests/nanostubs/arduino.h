#pragma once
#include <stdint.h>
#include <cstdio>
#include <sstream>
#include <string>
using byte=uint8_t;
constexpr int A0=14,A1=15,A2=16,A3=17,A4=18;
inline uint32_t nanoTime=0;
inline uint16_t nanoPressures[5]={1000,1000,1000,1000,1000};
inline uint32_t millis() {return nanoTime;}
inline void delay(unsigned n) {nanoTime+=n;}
inline int analogRead(int p) {return nanoPressures[p-A0];}
class SerialFake {
 public: std::string output; void begin(unsigned) {}
 template<class T> void print(T v) {std::ostringstream s;s<<v;output+=s.str();}
 template<class T> void println(T v) {print(v);output+='\n';}
};
inline SerialFake Serial;
