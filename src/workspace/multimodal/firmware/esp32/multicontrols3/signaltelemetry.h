#pragma once
#include <WiFi.h>
#include "SignalFrames.h"
#include "NetworkSocket.h"
class SignalTelemetry {
 public:
  SignalFrames frames;
  void begin(uint32_t id,uint32_t now) {
#if defined(_WIN32)
    WSADATA data; WSAStartup(MAKEWORD(2,2),&data);
#endif
    frames.begin(id,now);
  }
  void tick(uint32_t nowMs) {
    if(WiFi.status()!=WL_CONNECTED) { close(); return; }
    if(listener<0) {
      listener=::socket(AF_INET,SOCK_STREAM,0); if(listener<0) return;
      int on=1; setsockopt(listener,SOL_SOCKET,SO_REUSEADDR,reinterpret_cast<const char*>(&on),sizeof(on));
      nonblocking(listener); sockaddr_in addr={}; addr.sin_family=AF_INET; addr.sin_port=htons(9010); addr.sin_addr.s_addr=INADDR_ANY;
      if(::bind(listener,reinterpret_cast<sockaddr*>(&addr),sizeof(addr))<0 || ::listen(listener,1)<0) { close(); return; }
    }
    intptr_t incoming=::accept(listener,nullptr,nullptr);
    if(incoming>=0) {
      if(client>=0) closeSocket(incoming);
      else { client=incoming; nonblocking(client); sent=length=0; frames.discard(); progress=nowMs; }
    }
    if(client<0) { frames.discard(); return; }
    char command; int received=::recv(client,&command,1,NONBLOCK_SEND_FLAGS);
    // Read-only stream: no commands, uploads or arbitrary replay requests.
    if(received>=0 || !wouldBlock()) { disconnect(); return; }
    if(!length && frames.take(pending,sizeof(pending))) { length=strlen(pending); progress=nowMs; }
    if(length) {
      int n=::send(client,pending+sent,int(length-sent),NONBLOCK_SEND_FLAGS);
      if(n>0) { sent+=size_t(n); progress=nowMs; if(sent==length) sent=length=0; }
      else if((n<0 && !wouldBlock()) || uint32_t(nowMs-progress)>200) disconnect();
    }
  }
  void close() { disconnect(); if(listener>=0) { closeSocket(listener); listener=-1; } }
 private:
  intptr_t listener=-1,client=-1; char pending[768]={}; size_t sent=0,length=0; uint32_t progress=0;
  void disconnect() { if(client>=0) closeSocket(client); client=-1; sent=length=0; frames.discard(); }
};
