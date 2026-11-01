#ifndef CONTROL_PROTOCOL_H
#define CONTROL_PROTOCOL_H
#include <stdint.h>
#include <string.h>

#define CONTROL_FRAME_SIZE 9
#define CONTROL_VALID 1u
#define CONTROL_GRIP 2u
#define CONTROL_LEFT 1u
#define CONTROL_RIGHT 2u
#define CONTROL_TIMEOUT_MS 400u

typedef struct {
    uint8_t sequence, flags, event_id, direction;
} ControlFrame;

typedef struct {
    uint8_t bytes[CONTROL_FRAME_SIZE], used;
} ControlParser;

static uint16_t Control_Crc(const uint8_t *data, uint8_t length) {
    uint16_t crc = 0xffffu;
    uint8_t i, bit;
    for (i = 0; i < length; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (bit = 0; bit < 8; ++bit)
            crc = (uint16_t)((crc & 0x8000u) ? (crc << 1) ^ 0x1021u : crc << 1);
    }
    return crc;
}

static void Control_Encode(const ControlFrame *frame, uint8_t *bytes) {
    uint16_t crc;
    bytes[0] = 0xa5; bytes[1] = 0x5a; bytes[2] = 1;
    bytes[3] = frame->sequence; bytes[4] = frame->flags;
    bytes[5] = frame->event_id; bytes[6] = frame->direction;
    crc = Control_Crc(bytes, 7);
    bytes[7] = (uint8_t)crc; bytes[8] = (uint8_t)(crc >> 8);
}

static uint8_t Control_ParseByte(ControlParser *parser, uint8_t byte, ControlFrame *frame) {
    uint16_t crc;
    parser->bytes[parser->used++] = byte;
    /* Slide over noise, including partial headers inside a damaged frame. */
    while (parser->used && (parser->bytes[0] != 0xa5 ||
           (parser->used > 1 && parser->bytes[1] != 0x5a))) {
        --parser->used;
        memmove(parser->bytes, parser->bytes + 1, parser->used);
    }
    if (parser->used < CONTROL_FRAME_SIZE) return 0;
    crc = Control_Crc(parser->bytes, 7);
    if (parser->bytes[2] == 1 && (parser->bytes[4] & ~3u) == 0 &&
        !(parser->bytes[4] == CONTROL_GRIP) && parser->bytes[6] <= CONTROL_RIGHT &&
        parser->bytes[7] == (uint8_t)crc && parser->bytes[8] == (uint8_t)(crc >> 8)) {
        frame->sequence = parser->bytes[3]; frame->flags = parser->bytes[4];
        frame->event_id = parser->bytes[5]; frame->direction = parser->bytes[6];
        parser->used = 0;
        return 1;
    }
    --parser->used;
    memmove(parser->bytes, parser->bytes + 1, parser->used);
    return 0;
}

typedef struct {
    uint32_t last_rx;
    uint8_t linked, blocked, valid, last_grip, last_sequence, last_event;
} RemoteGate;
typedef struct { uint8_t stop, start, direction; } RemoteAction;

static void RemoteGate_Init(RemoteGate *gate) {
    memset(gate, 0, sizeof(*gate)); gate->blocked = 1;
}

static void RemoteGate_Block(RemoteGate *gate) { gate->blocked = 1; }

static RemoteAction RemoteGate_Receive(RemoteGate *gate, const ControlFrame *frame, uint32_t now) {
    RemoteAction action = {0, 0, 0};
    uint8_t grip = (frame->flags & CONTROL_GRIP) != 0;
    uint8_t valid = (frame->flags & CONTROL_VALID) != 0;
    if (!gate->linked || (uint32_t)(now - gate->last_rx) > CONTROL_TIMEOUT_MS) {
        gate->linked = 1; gate->blocked = 1; gate->valid = valid;
        gate->last_rx = now; gate->last_sequence = frame->sequence;
        gate->last_event = frame->event_id; gate->last_grip = grip;
        action.stop = 1; /* Reconnect synchronizes; never replay old turns/start. */
        return action;
    }
    /* Old/duplicate transport frames must not keep a stale command alive. */
    if ((uint8_t)(frame->sequence - gate->last_sequence) == 0 ||
        (uint8_t)(frame->sequence - gate->last_sequence) > 127) return action;
    gate->last_sequence = frame->sequence; gate->last_rx = now; gate->valid = valid;
    if (!valid) {
        gate->blocked = 1; gate->last_grip = grip;
        gate->last_event = frame->event_id; action.stop = 1;
        return action;
    }
    if (!grip) {
        if (gate->last_grip) action.stop = 1;
        gate->blocked = 0;
    } else if (!gate->blocked && !gate->last_grip) action.start = 1;
    if (frame->event_id != gate->last_event && !gate->blocked)
        action.direction = frame->direction;
    gate->last_event = frame->event_id; gate->last_grip = grip;
    return action;
}

static uint8_t RemoteGate_Expire(RemoteGate *gate, uint32_t now) {
    if (gate->linked && (uint32_t)(now - gate->last_rx) > CONTROL_TIMEOUT_MS) {
        gate->linked = 0; gate->valid = 0; gate->blocked = 1;
        return 1;
    }
    return 0;
}
#endif
