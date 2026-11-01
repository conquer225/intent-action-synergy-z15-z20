#pragma once
#if defined(_WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib,"ws2_32.lib")
constexpr int NONBLOCK_SEND_FLAGS=0;
inline void nonblocking(intptr_t socket) {
  unsigned long on=1; ioctlsocket(socket,FIONBIO,&on);
  int immediate=1;
  setsockopt(socket,IPPROTO_TCP,TCP_NODELAY,reinterpret_cast<const char*>(&immediate),sizeof(immediate));
}
inline bool wouldBlock() { int e=WSAGetLastError(); return e==WSAEWOULDBLOCK || e==WSAEINTR; }
inline void closeSocket(intptr_t socket) { closesocket(socket); }
#else
#include <lwip/sockets.h>
#include <fcntl.h>
#include <errno.h>
constexpr int NONBLOCK_SEND_FLAGS=MSG_DONTWAIT;
inline void nonblocking(intptr_t socket) {
  fcntl(socket,F_SETFL,O_NONBLOCK);
  // A small ACK must leave now, even while earlier telemetry is unacknowledged.
  int immediate=1;
  setsockopt(socket,IPPROTO_TCP,TCP_NODELAY,reinterpret_cast<const char*>(&immediate),sizeof(immediate));
}
inline bool wouldBlock() { return errno==EAGAIN || errno==EWOULDBLOCK || errno==EINTR; }
inline void closeSocket(intptr_t socket) { ::close(socket); }
#endif
