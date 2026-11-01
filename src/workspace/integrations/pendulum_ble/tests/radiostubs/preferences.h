#pragma once
#include <cstddef>
class Preferences {
 public:
 bool begin(const char*,bool){return true;}
 size_t getBytesLength(const char*){return 0;}
 size_t getBytes(const char*,void*,size_t){return 0;}
 size_t putBytes(const char*,const void*,size_t n){return n;}
};
