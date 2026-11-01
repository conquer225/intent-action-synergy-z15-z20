#include <cassert>
#include <cstdio>
#include "../esp32/MultiControlS3/ControlInput.h"
#include "../esp32/MultiControlS3/ControlProtocol.h"

int main() {
    GripGate g;
    g.update(120, true); g.update(120, true);
    assert(!g.armed && !g.gripped); // Booting while gripping cannot start.
    g.update(50, true); assert(!g.armed);
    g.update(50, true); assert(g.armed && !g.gripped);
    g.update(100, true); assert(!g.gripped);
    g.update(75, true); g.update(100, true); assert(!g.gripped);
    g.update(100, true); assert(g.gripped);
    g.update(75, true); assert(g.gripped);
    g.update(50, true); assert(g.gripped);
    g.update(50, true); assert(!g.gripped);
    g.update(0, false); assert(!g.armed && !g.gripped);

    ContactGate contact;
    contact.update(1000, true, true); contact.update(1000, true, true);
    assert(!contact.armed && !contact.gripped); // Held at boot: wait for release.
    contact.update(0, false, true); assert(!contact.armed);
    contact.update(0, false, true); assert(contact.armed && !contact.gripped);
    contact.update(1000, true, true); assert(!contact.gripped);
    contact.update(0, false, true); // A brief touch cannot accumulate.
    contact.update(49, true, true); contact.update(49, true, true);
    assert(contact.armed && !contact.gripped); // Released noise need not be exactly zero.
    contact.update(499, true, true); contact.update(499, true, true); assert(!contact.gripped);
    contact.update(500, true, true); assert(!contact.gripped);
    contact.update(500, true, true); assert(contact.gripped);
    contact.update(300, true, true); contact.update(51, true, true); assert(contact.gripped);
    contact.update(50, true, true); assert(contact.gripped);
    contact.update(51, true, true); contact.update(50, true, true); assert(contact.gripped);
    contact.update(50, true, true); assert(!contact.gripped);
    contact.update(1000, true, true); contact.update(1000, true, true); assert(contact.gripped);
    contact.update(1000, false, true); assert(contact.gripped);
    contact.update(1000, false, true); assert(!contact.gripped && contact.armed);
    contact.update(10, true, true); contact.update(10, true, true); assert(!contact.gripped);
    contact.update(1000, true, true); contact.update(1000, true, true); assert(contact.gripped);
    contact.update(0, true, true); contact.update(0, true, true); assert(!contact.gripped);
    contact.update(1000, true, false); assert(!contact.armed && !contact.gripped);
    contact.update(NAN, true, true); assert(!contact.armed && !contact.gripped);

    TurnGate t;
    assert(!t.update(0, 0, true)); assert(!t.update(0, 200, true));
    assert(!t.update(25, 300, true)); assert(!t.update(25, 449, true));
    assert(t.update(25, 450, true) == 1);
    assert(!t.update(60, 1000, true)); assert(!t.update(-30, 1200, true));
    t.update(0, 1300, true); t.update(0, 1500, true);
    t.update(-25, 1600, true); assert(t.update(-25, 1750, true) == -1);
    t.update(0, 1800, false); assert(!t.armed);
    t.update(0, UINT32_MAX - 100, true); t.update(0, 100, true);
    assert(t.armed); // millis() rollover.
    t.update(26, 200, true); t.update(0, 250, true);
    t.update(26, 300, true); assert(!t.update(26, 449, true));
    assert(t.update(26, 450, true) == 1); // Short excursions do not accumulate.

    const uint8_t vector[] = {'1','2','3','4','5','6','7','8','9'};
    assert(Control_Crc(vector, 9) == 0x29b1);
    ControlParser parser = {}; ControlFrame input = {255, 1, 8, CONTROL_LEFT}, output = {};
    uint8_t bytes[9]; Control_Encode(&input, bytes);
    int decoded = 0;
    Control_ParseByte(&parser, 0x00, &output);
    Control_ParseByte(&parser, 0xa5, &output); // Partial header before good frame.
    for (uint8_t b : bytes) decoded += Control_ParseByte(&parser, b, &output);
    assert(decoded == 1 && output.sequence == 255 && output.event_id == 8);
    bytes[4] ^= 1;
    for (uint8_t b : bytes) assert(!Control_ParseByte(&parser, b, &output));
    Control_Encode(&input, bytes);
    decoded = 0;
    for (uint8_t b : bytes) decoded += Control_ParseByte(&parser, b, &output);
    assert(decoded == 1);
    input.flags = CONTROL_GRIP; Control_Encode(&input, bytes);
    for (uint8_t b : bytes) assert(!Control_ParseByte(&parser, b, &output));

    RemoteGate gate; RemoteGate_Init(&gate);
    input = {254, 3, 8, CONTROL_LEFT};
    assert(RemoteGate_Receive(&gate, &input, 0).stop);
    input.sequence = 255; assert(!RemoteGate_Receive(&gate, &input, 50).start);
    input.sequence = 0; input.flags = 1;
    assert(RemoteGate_Receive(&gate, &input, 100).stop && !gate.blocked);
    input.sequence = 1; input.flags = 3;
    assert(RemoteGate_Receive(&gate, &input, 150).start);
    input.sequence = 2; input.event_id = 9;
    assert(RemoteGate_Receive(&gate, &input, 200).direction == CONTROL_LEFT);
    input.sequence = 3; assert(!RemoteGate_Receive(&gate, &input, 250).direction);
    assert(!RemoteGate_Receive(&gate, &input, 400).start);
    assert(RemoteGate_Expire(&gate, 651)); // Duplicate did not extend heartbeat.
    assert(RemoteGate_Receive(&gate, &input, 700).stop);
    input.sequence = 4; assert(!RemoteGate_Receive(&gate, &input, 750).start);
    input.sequence = 5; input.flags = 1; RemoteGate_Receive(&gate, &input, 800);
    RemoteGate_Block(&gate);
    input.sequence = 6; input.flags = 3; assert(!RemoteGate_Receive(&gate, &input, 850).start);
    input.sequence = 7; input.flags = 1; RemoteGate_Receive(&gate, &input, 900);
    input.sequence = 8; input.event_id = 10;
    RemoteAction a = RemoteGate_Receive(&gate, &input, 950);
    assert(!a.stop && a.direction == CONTROL_LEFT); // Relaxed frames allow standalone turns.
    input.sequence = 9; a = RemoteGate_Receive(&gate, &input, 1000);
    assert(!a.stop && !a.direction);
    input.sequence = 10; input.flags = 0;
    assert(RemoteGate_Receive(&gate, &input, 1050).stop && gate.blocked);
    std::puts("Input/protocol tests passed.");
}
