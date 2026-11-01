#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../esp32/MultiControlS3/BridgeProtocol.h"
using namespace pendulum_bridge;
constexpr uint32_t PEER = 0x6401a8c0UL, OTHER = 0x6501a8c0UL;
constexpr uint32_t SESSION = 0x12345678UL, NONCE = 0xaabbccddUL;

static Message wireRoundTrip(const Message &message) {
  uint8_t bytes[WIRE_SIZE]; Message decoded;
  encode(message, bytes); assert(decode(bytes, sizeof(bytes), decoded)); return decoded;
}
static Message control(uint32_t sequence, uint8_t flags, uint8_t event = 0, uint8_t direction = 0) {
  Message m = make(CONTROL, SESSION, NONCE, sequence);
  ControlFrame f = {uint8_t(sequence), flags, event, direction}; setControl(m, f); return wireRoundTrip(m);
}
static GatewayAction start(GatewaySession &gateway, uint32_t now = 500) {
  auto hello = wireRoundTrip(make(HELLO, SESSION, 0, 0));
  auto a = gateway.receive(hello, PEER, PORT, now, NONCE);
  assert(a.reply && a.response.type == CHALLENGE && a.response.nonce == NONCE && !a.serial);
  a = gateway.receive(wireRoundTrip(make(READY, SESSION, NONCE, 1)), PEER, PORT, now + 10, 9);
  assert(a.serial && a.output.flags == 0 && a.reply && a.response.type == ACK);
  assert(gateway.active() && !gateway.isArmed()); return a;
}
static void codecTests() {
  const Message original = control(2, CONTROL_VALID, 77, CONTROL_LEFT);
  uint8_t bytes[WIRE_SIZE]; encode(original, bytes);
  Message decoded;
  assert(decode(bytes, sizeof(bytes), decoded));
  assert(decoded.session == SESSION && decoded.nonce == NONCE && decoded.sequence == 2);
  ControlFrame frame; assert(readControl(decoded, frame)); assert(frame.event_id == 77);
  assert(!decode(bytes, WIRE_SIZE - 1, decoded)); assert(!decode(bytes, WIRE_SIZE + 1, decoded));
  for (unsigned i = 0; i < WIRE_SIZE; ++i) {
    bytes[i] ^= 0x40; assert(!decode(bytes, sizeof(bytes), decoded)); bytes[i] ^= 0x40;
  }
  Message damaged = original; damaged.payload[8] ^= 1;
  encode(damaged, bytes); assert(!decode(bytes, sizeof(bytes), decoded)); // valid envelope CRC, invalid inner CRC
  damaged = original; damaged.payload[13] = 1; encode(damaged, bytes);
  assert(!decode(bytes, sizeof(bytes), decoded));
  damaged = control(3, CONTROL_VALID); damaged.payload[4] = CONTROL_GRIP;
  write16(damaged.payload + 7, Control_Crc(damaged.payload, 7)); encode(damaged, bytes);
  assert(!decode(bytes, sizeof(bytes), decoded)); // grip cannot be set without valid
  StmStatus s; s.state = 14; s.target = -408; s.linked = 1; s.blocked = 0;
  s.fresh = 1; s.report = 34; s.age = 200;
  Message m = make(STATUS, SESSION, NONCE, 40); setStatus(m, s); m = wireRoundTrip(m);
  StmStatus received; assert(readStatus(m, received));
  assert(received.target == -408 && received.report == 34 && received.age == 200);
  m.payload[4] = 2; encode(m, bytes); assert(!decode(bytes, sizeof(bytes), decoded));
}
static void gateIntegrationTests() {
  GatewaySession bridge; bridge.begin(0);
  assert(!bridge.receive(make(HELLO, SESSION, 0, 0), PEER, PORT, BOOT_GUARD_MS - 1, NONCE).reply);
  RemoteGate stm; RemoteGate_Init(&stm);
  auto a = start(bridge); auto action = RemoteGate_Receive(&stm, &a.output, 510);
  assert(action.stop && stm.blocked);
  a = bridge.receive(control(2, CONTROL_VALID | CONTROL_GRIP, 99, CONTROL_LEFT), PEER, PORT, 520, 1);
  assert(a.serial && a.output.flags == 0 && !bridge.isArmed());
  action = RemoteGate_Receive(&stm, &a.output, 520); assert(action.stop && !action.start && !action.direction);
  a = bridge.receive(control(3, CONTROL_VALID, 99, CONTROL_LEFT), PEER, PORT, 530, 1);
  assert(a.serial && a.output.direction == 0 && bridge.isArmed());
  action = RemoteGate_Receive(&stm, &a.output, 530); assert(!action.start && !action.direction && !stm.blocked);
  a = bridge.receive(control(4, CONTROL_VALID | CONTROL_GRIP, 99, CONTROL_LEFT), PEER, PORT, 540, 1);
  action = RemoteGate_Receive(&stm, &a.output, 540); assert(action.start && !action.direction);
  a = bridge.receive(control(5, CONTROL_VALID | CONTROL_GRIP, 100, CONTROL_RIGHT), PEER, PORT, 550, 1);
  action = RemoteGate_Receive(&stm, &a.output, 550); assert(!action.start && action.direction == CONTROL_RIGHT);
  a = bridge.receive(control(6, CONTROL_VALID | CONTROL_GRIP, 100, CONTROL_RIGHT), PEER, PORT, 560, 1);
  action = RemoteGate_Receive(&stm, &a.output, 560); assert(!action.direction);
  // Duplicate, reordered, invalid CRC, wrong IP/port/session/nonce do not keep a command alive.
  assert(!bridge.receive(control(6, CONTROL_VALID | CONTROL_GRIP), PEER, PORT, 700, 1).reply);
  assert(!bridge.receive(control(4, CONTROL_VALID | CONTROL_GRIP), PEER, PORT, 705, 1).reply);
  assert(!bridge.receive(control(7, CONTROL_VALID | CONTROL_GRIP), OTHER, PORT, 710, 1).reply);
  assert(!bridge.receive(control(7, CONTROL_VALID | CONTROL_GRIP), PEER, PORT + 1, 710, 1).reply);
  Message wrong = control(7, CONTROL_VALID | CONTROL_GRIP); wrong.session++;
  assert(!bridge.receive(wrong, PEER, PORT, 715, 1).reply);
  wrong = control(7, CONTROL_VALID | CONTROL_GRIP); wrong.nonce++;
  assert(!bridge.receive(wrong, PEER, PORT, 720, 1).reply);
  wrong = control(7, CONTROL_VALID | CONTROL_GRIP); wrong.payload[8] ^= 1;
  assert(!bridge.receive(wrong, PEER, PORT, 725, 1).reply);
  assert(!bridge.expire(809).serial);
  a = bridge.expire(810); assert(a.serial && a.output.flags == 0 && !bridge.active());
  action = RemoteGate_Receive(&stm, &a.output, 810); assert(action.stop && stm.blocked);
  assert(!bridge.expire(1000).serial); // never synthetic continuing keepalive
  assert(!bridge.receive(control(8, CONTROL_VALID | CONTROL_GRIP), PEER, PORT, 1000, 1).reply);
  a = bridge.receive(make(HELLO, SESSION, 0, 0), PEER, PORT, 1000, NONCE + 1);
  assert(a.response.nonce == NONCE + 1);
  assert(!bridge.receive(make(READY, SESSION, NONCE, 1), PEER, PORT, 1010, 1).reply);
  a = bridge.receive(make(READY, SESSION, NONCE + 1, 1), PEER, PORT, 1010, 1);
  assert(a.serial && !bridge.isArmed());
  Message staleGrip = control(2, CONTROL_VALID | CONTROL_GRIP, 100, CONTROL_RIGHT); staleGrip.nonce++;
  a = bridge.receive(staleGrip, PEER, PORT, 1020, 1); assert(a.serial && a.output.flags == 0);
  assert(!bridge.isArmed());
}
static void stopAndRetryTests() {
  GatewaySession bridge; bridge.begin(0); start(bridge);
  auto ready = make(READY, SESSION, NONCE, 1);
  assert(bridge.receive(ready, PEER, PORT, 650, 1).reply);
  assert(bridge.expire(760).serial); // READY replay did not refresh 510 lease
  bridge.begin(0); start(bridge);
  bridge.receive(control(2, CONTROL_VALID), PEER, PORT, 520, 1);
  bridge.receive(control(3, CONTROL_VALID | CONTROL_GRIP), PEER, PORT, 530, 1);
  auto stopped = bridge.receive(control(4, 0), PEER, PORT, 531, 1);
  assert(stopped.serial && stopped.output.flags == 0 && !bridge.isArmed());
  auto held = bridge.receive(control(5, CONTROL_VALID | CONTROL_GRIP), PEER, PORT, 540, 1);
  assert(held.output.flags == 0 && !bridge.isArmed());
  bridge.receive(control(6, CONTROL_VALID), PEER, PORT, 550, 1); assert(bridge.isArmed());
  auto lost = bridge.disconnect(); assert(lost.serial && lost.output.flags == 0);
  assert(!bridge.disconnect().serial);
  assert(newer(0, 0xffffffffUL) && !newer(0xfffffffeUL, 1));
}
static void clientTests() {
  ClientSession client; client.begin(SESSION, 100);
  assert(client.state() == ClientSession::DISCOVER && !client.linked());
  assert(client.handshake().type == HELLO);
  Message challenge = make(CHALLENGE, SESSION, NONCE, 0);
  assert(!client.receive(challenge, PEER, PORT + 1, 110));
  assert(client.receive(challenge, PEER, PORT, 110));
  assert(client.state() == ClientSession::CONFIRM && client.handshake().type == READY);
  StmStatus status;
  Message ack = make(ACK, SESSION, NONCE, 1); setStatus(ack, status);
  assert(!client.receive(ack, OTHER, PORT, 120));
  assert(client.receive(ack, PEER, PORT, 120) && client.linked());
  ControlFrame f = {9, CONTROL_VALID, 0, 0};
  auto packet = client.control(f); assert(packet.sequence == 2);
  ack.sequence = 3; assert(!client.receive(ack, PEER, PORT, 130)); // ACK for unsent command
  ack.sequence = 2; assert(client.receive(ack, PEER, PORT, 140));
  assert(!client.receive(ack, PEER, PORT, 300));
  Message telemetry = make(STATUS, SESSION, NONCE, 2); setStatus(telemetry, status);
  assert(client.receive(telemetry, PEER, PORT, 380));
  assert(!client.expired(389) && client.expired(390)); // telemetry/replayed ACK cannot keep alive
  assert(!client.receive(ack, PEER, PORT, 400));
  client.begin(SESSION + 1, 400);
  assert(!client.receive(challenge, PEER, PORT, 410));
  assert(client.expired(1400));
}
static void statusParserTests() {
  StmStatus status;
  const char *valid = "S,14,-408,1,0";
  assert(parseStatusLine(valid, strlen(valid), status)); assert(status.state == 14 && status.target == -408);
  const char *bad[] = {"S,1,0,1,2", "S,1,0,1,0,x", "S,1,99999999999999999,1,0", "S,-1,0,1,0", "S,1,9000,1,0", "S,1,0,,0", "S,1,0,1", "S,1,0,1,0\n"};
  for (const char *line : bad) assert(!parseStatusLine(line, strlen(line), status));
}
int main() {
  codecTests(); gateIntegrationTests(); stopAndRetryTests(); clientTests(); statusParserTests();
  puts("bridge protocol, lease, arming, STM integration and status tests passed");
}
