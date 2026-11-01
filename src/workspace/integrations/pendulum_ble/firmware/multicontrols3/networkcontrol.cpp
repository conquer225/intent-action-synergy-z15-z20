#include "NetworkControl.h"
#include "NetworkSocket.h"

void NetworkControl::begin(NetworkHandler h, NetworkLost l, NetworkStatus s) {
#if defined(_WIN32)
  WSADATA data; WSAStartup(MAKEWORD(2,2),&data);
#endif
  handler=h; lost=l; status=s;
}
void NetworkControl::closeClient(Client &client) {
  if (client.socket>=0) { closeSocket(client.socket); client.socket=-1; }
  CommandSource source=client.session.source;
  bool active=client.session.active;
  client.session.clear(); client.used=client.pendingUsed=client.sent=0;
  if (active && lost) lost(source);
}
bool NetworkControl::fresh(CommandSource source,uint32_t now) const {
  if (source==CommandSource::NONE) return false;
  for (const Client &c:clients)
    if (c.socket>=0 && c.session.active && c.session.source==source && !c.session.expired(now)) return true;
  return false;
}
bool NetworkControl::queue(Client &client, JsonDocument &doc) {
  size_t size=measureJson(doc);
  if (size>NETWORK_LINE_LIMIT) { closeClient(client); return false; }
  if (client.sent) {
    memmove(client.pending,client.pending+client.sent,client.pendingUsed-client.sent);
    client.pendingUsed-=client.sent; client.sent=0;
  }
  if (client.pendingUsed+size+1>sizeof(client.pending)) { closeClient(client); return false; }
  size_t written=serializeJson(doc,client.pending+client.pendingUsed,size+1);
  client.pendingUsed+=written; client.pending[client.pendingUsed++]='\n';
  return true;
}
void NetworkControl::request(Client &client,uint32_t now) {
  NetworkRequest req; const char *error=nullptr;
  bool parsed=parseNetworkRequest(client.line,client.used,req,error);
  JsonDocument reply; reply["v"]=1; reply["seq"]=parsed?req.sequence:0;
  bool ok=parsed && client.session.accepts(req,now,error);
  if (ok && req.action==CommandAction::HELLO) {
    for (const Client &other:clients)
      if (&other!=&client && other.session.active && other.session.source==req.source) {
        ok=false; error="source_in_use"; break;
      }
  }
  if (ok) {
    if (req.action!=CommandAction::HELLO && req.action!=CommandAction::HEARTBEAT &&
        req.action!=CommandAction::STATUS) ok=handler && handler(req,error);
    client.session.consume(req,now,ok);
  }
  reply["ok"]=ok;
  if (!ok) reply["error"]=error?error:"rejected";
  if (ok && (req.action==CommandAction::STATUS || req.action==CommandAction::HELLO))
    status(reply["status"].to<JsonObject>());
  queue(client,reply);
}
void NetworkControl::tick(uint32_t now) {
  if (WiFi.status()!=WL_CONNECTED) {
    for (Client &c:clients) if (c.socket>=0) closeClient(c);
    if (listener>=0) { closeSocket(listener); listener=-1; }
    return;
  }
  if (listener<0) {
    listener=::socket(AF_INET,SOCK_STREAM,0);
    if (listener<0) return;
    int on=1; setsockopt(listener,SOL_SOCKET,SO_REUSEADDR,reinterpret_cast<const char*>(&on),sizeof(on));
    nonblocking(listener);
    sockaddr_in addr={}; addr.sin_family=AF_INET; addr.sin_port=htons(9000); addr.sin_addr.s_addr=INADDR_ANY;
    if (::bind(listener,reinterpret_cast<sockaddr*>(&addr),sizeof(addr))<0 || ::listen(listener,3)<0) {
      closeSocket(listener); listener=-1; return;
    }
  }
  intptr_t incoming=::accept(listener,nullptr,nullptr);
  if (incoming>=0) {
    nonblocking(incoming);
    bool assigned=false;
    for (Client &c:clients) if (c.socket<0) {
      c=Client{}; c.socket=incoming; c.openedMs=now; assigned=true; break;
    }
    if (!assigned) closeSocket(incoming);
  }
  for (Client &c:clients) {
    if (c.socket<0) continue;
    if (c.session.expired(now) || (!c.session.active && uint32_t(now-c.openedMs)>500)) {
      closeClient(c); continue;
    }
    // One bounded non-blocking chunk per loop. Floods cannot monopolize sampling.
    char bytes[128]; int count=::recv(c.socket,bytes,sizeof(bytes),NONBLOCK_SEND_FLAGS);
    if (!count || (count<0 && !wouldBlock())) {
      closeClient(c); continue;
    }
    for (int i=0;i<count && c.socket>=0;++i) {
      char byte=bytes[i];
      if (byte=='\r') continue;
      if (byte=='\n') {
        c.line[c.used]=0;
        if (c.used) request(c,now);
        c.used=0;
      } else if (c.used<NETWORK_LINE_LIMIT) c.line[c.used++]=byte;
      else { closeClient(c); break; }
    }
    if (c.socket<0) continue;
    if (c.session.active && !c.pendingUsed && uint32_t(now-c.lastTelemetryMs)>=100) {
      JsonDocument doc; doc["v"]=1; doc["type"]="telemetry";
      status(doc["status"].to<JsonObject>()); c.lastTelemetryMs=now;
      queue(c,doc);
    }
    if (c.socket>=0 && c.sent<c.pendingUsed) {
      int n=::send(c.socket,c.pending+c.sent,int(c.pendingUsed-c.sent),NONBLOCK_SEND_FLAGS);
      if (n>0) {
        c.sent+=size_t(n);
        if (c.sent==c.pendingUsed) c.sent=c.pendingUsed=0;
      } else if (n<0 && !wouldBlock()) closeClient(c);
    }
  }
}
