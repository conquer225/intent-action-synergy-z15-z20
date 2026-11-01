#include <cassert>
#include <cstdio>
#include <string>
#include "../esp32c3/PendulumBridgeC3/PendulumBridgeC3.ino"
int main() {
  setup();
#ifdef TEST_C3_EMPTY_PASSWORD
  assert(!apReady && WiFi.radio == WIFI_OFF && WiFi.apCalls == 0);
  fakeMillis=6000; loop();
  assert(!apReady && !udpReady && WiFi.apCalls == 0);
  puts("C3 missing credentials keep AP and UDP disabled");
#else
  assert(Serial1.baud == 9600 && Serial1.rx == 1 && Serial1.tx == 0);
  assert(Serial.baud == 115200);
  puts("C3 UART isolation passed");
  assert(WiFi.radio == WIFI_AP && WiFi.apCalls == 1);
  assert(WiFi.ssid == "Test-Control" && WiFi.password == "test-only-12345");
  fakeMillis = 500;
  Message hello = make(HELLO, 0x12345678, 0, 0);
  uint8_t bytes[WIRE_SIZE]; encode(hello, bytes);
  WiFiUDP::incoming.push_back({0x0204a8c0, PORT, {bytes, bytes + WIRE_SIZE}});
  loop();
  assert(WiFiUDP::outgoing.size() == 1);
  Message challenge;
  assert(decode(WiFiUDP::outgoing.back().bytes.data(), WIRE_SIZE, challenge));
  assert(challenge.type == CHALLENGE);
  puts("C3 AP UDP discovery passed with station status disconnected");
  auto send = [](Message message) {
    uint8_t packet[WIRE_SIZE]; encode(message, packet);
    WiFiUDP::incoming.push_back({0x0204a8c0, PORT, {packet, packet + WIRE_SIZE}});
    loop();
  };
  send(make(READY, challenge.session, challenge.nonce, 1));
  assert(Serial1.output.size() == CONTROL_FRAME_SIZE);
  assert(Serial.output.empty());
  // Independent UART frame decoder checks the physical forwarding boundary.
  assert(Serial1.output[0] == 0xa5 && Serial1.output[1] == 0x5a && Serial1.output[4] == 0);
  const std::string feedback = "S,14,-408,1,1\r\n";
  for (size_t i=0; i<6; ++i) Serial1.input.push_back(feedback[i]);
  loop(); assert(!currentStatus(fakeMillis).fresh);
  for (size_t i=6; i<feedback.size(); ++i) Serial1.input.push_back(feedback[i]);
  loop();
  StmStatus status;
  Message report;
  assert(decode(WiFiUDP::outgoing.back().bytes.data(), WIRE_SIZE, report));
  assert(readStatus(report, status) && status.fresh && status.target == -408 && status.blocked == 1);
  const std::string raw="T,200,2050,-12,35\n";
  const size_t uartBeforeTelemetry=Serial1.output.size();
  for(char c:raw)Serial1.input.push_back(c);
  loop();
  assert(WiFiUDP::outgoing.back().port==9011);
  const std::string telemetry(WiFiUDP::outgoing.back().bytes.begin(),WiFiUDP::outgoing.back().bytes.end());
  assert(telemetry.find("\"adc\":2050")!=std::string::npos);
  assert(Serial1.output.size()==uartBeforeTelemetry);
  const size_t sentBeforeExpiry = Serial1.output.size();
  Serial.freeBytes = 0;
  fakeMillis += LEASE_MS; loop();
  assert(Serial1.output.size() == sentBeforeExpiry + CONTROL_FRAME_SIZE);
  assert(Serial1.output[sentBeforeExpiry + 4] == 0 && !gateway.active());
  assert(Serial.blockedWrites == 0);
  fakeMillis += STATUS_FRESH_MS; loop();
  assert(!currentStatus(fakeMillis).fresh);
  // A large malformed packet must release the receive buffer before discovery.
  WiFiUDP::incoming.push_back({0x0204a8c0, PORT, std::vector<uint8_t>(1200, 0xff)});
  const size_t replies = WiFiUDP::outgoing.size();
  send(make(HELLO, 0x98765432, 0, 0));
  assert(WiFiUDP::outgoing.size() == replies + 1);
  WiFi.apResult = false; WiFi.mode(WIFI_OFF); fakeMillis += 5000; loop();
  assert(!udpReady && !apReady);
  const size_t offlineReplies = WiFiUDP::outgoing.size();
  send(make(HELLO, 123, 0, 0));
  assert(WiFiUDP::outgoing.size() == offlineReplies);
  WiFi.apResult = true; fakeMillis += 5000; loop(); loop();
  assert(apReady && udpReady);
  puts("C3 UART feedback, lease stop, blocked USB, malformed UDP and AP retry passed");
  Serial.freeBytes = 1024; fakeMillis += 1000; loop();
  const std::string diagnostic(Serial.output.begin(), Serial.output.end());
  assert(diagnostic.find("BRIDGE,") != std::string::npos);
  assert(diagnostic.find("stm_report:1") != std::string::npos);
  assert(diagnostic.find(AP_PASSWORD) == std::string::npos);
  Serial.freeBytes = 0; fakeMillis += 1000; loop();
  assert(Serial.blockedWrites == 0);
  puts("C3 bounded diagnostics passed");
#endif
}
