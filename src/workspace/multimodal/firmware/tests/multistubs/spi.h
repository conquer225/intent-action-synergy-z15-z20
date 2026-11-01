#pragma once
class SPIClass {
 public:
  int sck = -1, miso = -1, mosi = -1, csn = -1;
  bool begin(int a, int b, int c, int d) { sck=a; miso=b; mosi=c; csn=d; return true; }
};
inline SPIClass SPI;
