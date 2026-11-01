#pragma once
#include <cstdint>
#include <cstddef>
inline uint64_t fakeUs=0;inline uint32_t millis(){return fakeUs/1000;}inline uint32_t micros(){return fakeUs;}
constexpr int INPUT=0,ADC_11db=0;
inline void pinMode(int,int){} inline void analogSetPinAttenuation(int,int){}
inline int analogRead(int){return 2048;}
struct TestSerial {
 template<class... T> void printf(const char*,T...){}
 template<class... T> void print(T...){}
 template<class... T> void println(T...){}
};
inline TestSerial Serial;
