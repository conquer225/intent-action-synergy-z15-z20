#pragma once
#include <winsock2.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include "../esp32/MultiControlS3/MultiControlS3.ino"
using namespace pendulum_bridge;
inline GatewaySession gateway;
inline bool bridgeAlive=true, stmReporting=true;
inline uint8_t reportedStmState=0, reportedStmBlocked=0;
inline size_t udpRead=0;
inline std::vector<ControlFrame> uartFrames;
inline void pumpGateway() {
  gateway.expire(millis());
  while (udpRead<WiFiUDP::outgoing.size()) {
    auto packet=WiFiUDP::outgoing[udpRead++];
    if (!bridgeAlive) continue;
    Message msg; assert(decode(packet.bytes.data(),packet.bytes.size(),msg));
    auto a=gateway.receive(msg,uint32_t(WiFi.localIP()),PORT,millis(),0xabcdef);
    if (a.serial) {
      uartFrames.push_back(a.output);
      reportedStmBlocked=(a.output.flags&CONTROL_VALID)?0:1;
      if (reportedStmBlocked) reportedStmState=0;
    }
    if (a.reply) {
      StmStatus s; s.fresh=stmReporting; s.report=uint32_t(uartFrames.size());
      s.age=0; s.linked=1; s.blocked=reportedStmBlocked; s.state=reportedStmState;
      if (a.response.type==ACK) setStatus(a.response,s);
      BridgeFakeDatagram reply; reply.ip=uint32_t(IPAddress(10,0,0,10)); reply.port=PORT;
      reply.bytes.resize(WIRE_SIZE); encode(a.response,reply.bytes.data());
      WiFiUDP::incoming.push_back(reply);
    }
  }
}
inline void runFor(unsigned ms) {
  uint64_t until=fakeUs+1000ULL*ms;
  while (fakeUs<until) { fakeUs+=200; loop(); pumpGateway(); }
}
inline void command(const char *text) { Serial.feed(text); Serial.feed("\n"); runFor(20); }
inline JsonDocument status() { JsonDocument d; buildNetworkStatus(d.to<JsonObject>()); return d; }
inline void saveConfirmedPoses() {
  GloveController provision; provision.begin();
  const int16_t open[6]={180,180,180,180,180,180}, close[6]={110,110,110,110,110,0};
  assert(provision.capturePose(false,open)); assert(provision.capturePose(true,close));
  assert(provision.savePoses());
}
inline void assertOpen() {
  auto d=status(); for (unsigned i=0;i<6;++i) assert(d["hand"]["angles"][i].as<int>()==180);
}
inline void assertClosed() {
  auto d=status(); for (unsigned i=0;i<5;++i) assert(d["hand"]["angles"][i].as<int>()==110);
  assert(d["hand"]["angles"][5].as<int>()==0);
}
inline SOCKET connectSource() {
  SOCKET sock=socket(AF_INET,SOCK_STREAM,0); assert(sock!=INVALID_SOCKET);
  sockaddr_in addr={}; addr.sin_family=AF_INET; addr.sin_port=htons(9000);
  addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
  assert(connect(sock,reinterpret_cast<sockaddr*>(&addr),sizeof(addr))==0);
  unsigned long on=1; ioctlsocket(sock,FIONBIO,&on); runFor(1); return sock;
}
inline JsonDocument ask(SOCKET sock,const char *source,unsigned seq,const char *device,const char *action,const char *extra="") {
  char line[1024]; snprintf(line,sizeof(line),"{\"v\":1,\"source\":\"%s\",\"seq\":%u,\"device\":\"%s\",\"action\":\"%s\"%s}\n",source,seq,device,action,extra);
  assert(send(sock,line,int(strlen(line)),0)==int(strlen(line)));
  std::string received;
  for (int attempt=0;attempt<40;++attempt) {
    runFor(1); Sleep(1); char b[4096]; int n=recv(sock,b,sizeof(b),0);
    if (n>0) received.append(b,n);
    size_t end;
    while ((end=received.find('\n'))!=std::string::npos) {
      std::string frame=received.substr(0,end); received.erase(0,end+1);
      JsonDocument d; assert(!deserializeJson(d,frame));
      if (d["seq"].is<unsigned>() && d["seq"].as<unsigned>()==seq) return d;
    }
  }
  assert(false && "missing production TCP ACK"); return JsonDocument();
}
