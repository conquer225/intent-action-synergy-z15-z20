#include <assert.h>
#include <stdio.h>
#include "../esp32/MultiControlS3/PendulumLink.h"
using namespace pendulum_bridge;
uint32_t bridgeFakeMillis = 0;
const uint32_t gatewayIp = uint32_t(IPAddress(10,0,0,10));

static void deliver(Message message, uint32_t ip = gatewayIp, bool corrupt = false) {
  BridgeFakeDatagram packet; packet.ip = ip; packet.port = PORT; packet.bytes.resize(WIRE_SIZE);
  encode(message, packet.bytes.data()); if (corrupt) packet.bytes[31] ^= 1;
  WiFiUDP::incoming.push_back(packet);
}
static Message latest() {
  assert(!WiFiUDP::outgoing.empty()); Message message;
  const auto &packet = WiFiUDP::outgoing.back();
  assert(decode(packet.bytes.data(), packet.bytes.size(), message)); return message;
}
static void tick(PendulumLink &link, uint32_t now, uint8_t flags = 0) {
  bridgeFakeMillis = now; ControlFrame desired = {11, flags, 20, CONTROL_LEFT}; link.tick(now, desired);
}
static Message connect(PendulumLink &link, uint32_t now) {
  tick(link, now); Message hello = latest(); assert(hello.type == HELLO);
  assert(WiFiUDP::outgoing.back().ip == uint32_t(IPAddress(10,0,0,255)));
  Message challenge = make(CHALLENGE, hello.session, 0x91672035, 0); deliver(challenge);
  tick(link, now + 1); Message ready = latest();
  assert(ready.type == READY && WiFiUDP::outgoing.back().ip == gatewayIp);
  StmStatus status; Message ack = make(ACK, ready.session, ready.nonce, 1); setStatus(ack, status);
  deliver(ack); tick(link, now + 2, CONTROL_VALID | CONTROL_GRIP);
  assert(link.linked()); Message control = latest(); assert(control.type == CONTROL && control.sequence == 2);
  return control;
}
static void leaseAndRouting() {
  PendulumLink link; link.begin(); WiFi.state = WL_CONNECTED;
  WiFiUDP::outgoing.clear(); Message command = connect(link, 500);
  assert(link.reconnectCount() == 1 && !link.stmFresh(502) && link.stmState() == -1);
  StmStatus status; status.fresh = 1; status.report = 1; status.age = 100;
  status.state = 11; status.target = -408; status.linked = 1; status.blocked = 0;
  Message ack = make(ACK, command.session, command.nonce, 2); setStatus(ack, status);
  deliver(ack); tick(link, 510);
  assert(link.stmFresh(510) && link.stmState() == 11 && link.stmBlocked() == 0);
  Message telemetry = make(STATUS, command.session, command.nonce, 2); setStatus(telemetry, status);
  deliver(telemetry); deliver(ack); deliver(ack, uint32_t(IPAddress(10,0,0,30))); deliver(ack, gatewayIp, true);
  tick(link, 759); assert(link.linked()); // all of these cannot refresh the 510 ACK
  tick(link, 760); assert(!link.linked() && link.reconnectCount() == 2 && !link.stmFresh(760));
  Message hello = latest(); assert(hello.type == HELLO && hello.session != command.session);
  deliver(ack); tick(link, 761); assert(!link.linked()); // stale-session ACK discarded
  WiFi.state = 0; tick(link, 762); assert(!link.linked());
}
static void immediateStopAndReconnection() {
  PendulumLink link; link.begin(); WiFi.state = WL_CONNECTED;
  Message command = connect(link, 1000);
  bridgeFakeMillis = 1003; link.forceStop(); Message stop = latest();
  ControlFrame decoded; assert(readControl(stop, decoded));
  assert(stop.sequence == command.sequence + 1 && decoded.flags == 0 && decoded.direction == 0);
  assert(WiFiUDP::outgoing.back().ip == gatewayIp);
  WiFi.state = 0; tick(link, 1004); assert(link.reconnectCount() == 2);
  WiFi.state = WL_CONNECTED; Message connected = connect(link, 1100);
  assert(link.reconnectCount() == 3 && connected.session != command.session);
}
static void statusReportsDoNotRefreshSamples() {
  PendulumLink link; link.begin(); WiFi.state = WL_CONNECTED;
  Message command = connect(link, 2000);
  StmStatus status; status.fresh = 1; status.report = 10; status.age = 100;
  status.state = 10; status.blocked = 0;
  Message ack = make(ACK, command.session, command.nonce, command.sequence); setStatus(ack, status);
  deliver(ack); tick(link, 2010); assert(link.stmFresh(2010));
  // New ACKs keep the transport healthy, but cached report 10 cannot make the UART fresh forever.
  for (uint32_t now = 2060; now <= 2960; now += 50) {
    tick(link, now); command = latest();
    ack.sequence = command.sequence; status.age = uint16_t(now - 1910);
    status.fresh = status.age < STATUS_FRESH_MS; setStatus(ack, status);
    deliver(ack); tick(link, now + 1);
  }
  assert(link.linked() && !link.stmFresh(2961));
  status.report = 11; status.age = 10; status.fresh = 1;
  Message telemetry = make(STATUS, command.session, command.nonce, command.sequence); setStatus(telemetry, status);
  deliver(telemetry); tick(link, 2970); assert(link.stmFresh(2970));
}
static void neutralAcknowledgement() {
  PendulumLink link; link.begin(); WiFi.state=WL_CONNECTED;
  connect(link,3500); bridgeFakeMillis=3503;
  link.forceStop(); link.armNeutral();
  Message neutral=latest(); ControlFrame f;
  assert(readControl(neutral,f) && f.flags==CONTROL_VALID && f.direction==0 && !link.neutralReady());
  tick(link,3560,CONTROL_VALID|CONTROL_GRIP); neutral=latest();
  assert(readControl(neutral,f) && f.flags==CONTROL_VALID); // Never GRIP before neutral ACK.
  Message ack=make(ACK,neutral.session,neutral.nonce,neutral.sequence); StmStatus status; setStatus(ack,status);
  deliver(ack); tick(link,3561,CONTROL_VALID|CONTROL_GRIP); assert(link.neutralReady());
  tick(link,3610,CONTROL_VALID|CONTROL_GRIP);
  assert(readControl(latest(),f) && f.flags==(CONTROL_VALID|CONTROL_GRIP));
}
int main() {
  leaseAndRouting(); immediateStopAndReconnection(); statusReportsDoNotRefreshSamples(); neutralAcknowledgement();
  puts("PendulumLink actual adapter routing, stop, lease, reconnect and report freshness tests passed");
}
