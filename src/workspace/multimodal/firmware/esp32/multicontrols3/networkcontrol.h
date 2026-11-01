#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include "CommandProtocol.h"

typedef bool (*NetworkHandler)(const NetworkRequest &, const char *&);
typedef void (*NetworkLost)(CommandSource);
typedef void (*NetworkStatus)(JsonObject);
class NetworkControl {
 public:
  void begin(NetworkHandler handler, NetworkLost lost, NetworkStatus status);
  void tick(uint32_t now);
  bool fresh(CommandSource source, uint32_t now) const;
 private:
  struct Client {
    intptr_t socket=-1;
    SourceSession session;
    char line[NETWORK_LINE_LIMIT+1]={};
    size_t used=0;
    uint32_t openedMs=0, lastTelemetryMs=0;
    char pending[2048]={};
    size_t pendingUsed=0, sent=0;
  } clients[3];
  intptr_t listener=-1;
  NetworkHandler handler=nullptr;
  NetworkLost lost=nullptr;
  NetworkStatus status=nullptr;
  void closeClient(Client &client);
  bool queue(Client &client, JsonDocument &document);
  void request(Client &client, uint32_t now);
};
