#include "NetworkSocket.h"
#include <cassert>
#include <iostream>

int main() {
#if defined(_WIN32)
  WSADATA data;
  assert(WSAStartup(MAKEWORD(2, 2), &data) == 0);
#endif
  const intptr_t peer = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  assert(peer >= 0);
  nonblocking(peer);
  int immediate = 0;
#if defined(_WIN32)
  int size = sizeof(immediate);
#else
  socklen_t size = sizeof(immediate);
#endif
  assert(getsockopt(peer, IPPROTO_TCP, TCP_NODELAY,
                    reinterpret_cast<char *>(&immediate), &size) == 0);
  if (immediate != 1) {
    std::cerr << "Control ACK packets must not wait for Nagle coalescing\n";
    closeSocket(peer);
    return 1;
  }
  closeSocket(peer);
#if defined(_WIN32)
  WSACleanup();
#endif
  std::cout << "Immediate TCP packet policy passed\n";
}
