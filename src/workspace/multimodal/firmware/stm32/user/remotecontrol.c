#include "stm32f10x.h"
#include "Serial.h"
#include "Mode3.h"
#include "RemoteControl.h"
#include "ControlProtocol.h"
#include <stdio.h>
#include "AD.h"
#include "Encoder.h"
#include "Motor.h"

#define QUEUE_SIZE 8
typedef struct { ControlFrame frame; uint32_t received; } ReceivedFrame;
static ReceivedFrame queue[QUEUE_SIZE];
static volatile uint8_t writeIndex, readIndex, queueFault;
static volatile uint32_t clockMs;
static RemoteGate gate;
static ControlParser parser;
static uint32_t lastByteMs, lastReportMs;

void RemoteControl_Init(void) {
    RemoteGate_Init(&gate);
    memset(&parser, 0, sizeof(parser));
    writeIndex = readIndex = queueFault = 0;
    clockMs = lastByteMs = lastReportMs = 0;
}

void RemoteControl_Block(void) { RemoteGate_Block(&gate); }
uint8_t RemoteControl_Ready(void) { return gate.linked && gate.valid && !gate.blocked; }

/* Main loop: receive bytes and print status. Never print in the 1 ms ISR. */
void RemoteControl_Poll(void) {
    uint8_t byte, next;
    uint16_t count = 0;
    ControlFrame frame;
    uint32_t now = clockMs;
    Serial_PollTelemetry();
    if (Serial_TakeRxError()) {
        queueFault = 1;
        memset(&parser, 0, sizeof(parser));
    }
    if ((uint32_t)(now - lastByteMs) > 30) parser.used = 0;
    while (count++ < 128 && Serial_ReadByte(&byte)) {
        lastByteMs = now;
        if (Control_ParseByte(&parser, byte, &frame)) {
            next = (uint8_t)((writeIndex + 1) % QUEUE_SIZE);
            if (next == readIndex) { queueFault = 1; break; }
            queue[writeIndex].frame = frame;
            queue[writeIndex].received = now;
            __DMB();
            writeIndex = next;
        }
    }
    if ((uint32_t)(now - lastReportMs) >= 200) {
        char message[128];
        uint8_t state, linked, blocked;
        int16_t target,location,pwm;uint16_t adc;
        uint32_t mask = __get_PRIMASK();
        __disable_irq();
        state = Mode31_GetRunState(); target = Mode31_GetTarget();
        linked = gate.linked; blocked = gate.blocked;
        adc=AD_GetValue(1);location=Encoder_GetLocation(1);pwm=Motor_GetPWM(1);
        __set_PRIMASK(mask);
        sprintf(message, "S,%u,%d,%u,%u\nT,%lu,%u,%d,%d\n", state, target, linked, blocked,
            (unsigned long)now,adc,location,pwm);
        Serial_TryTelemetry(message);
        lastReportMs = now;
    }
}

/* Timer ISR owns the motor state and consumes complete, checked packets. */
void RemoteControl_Tick(void) {
    ++clockMs;
    if (queueFault) {
        queueFault = 0; readIndex = writeIndex;
        RemoteGate_Init(&gate);
        Mode31_RemoteStop();
    }
    while (readIndex != writeIndex) {
        ReceivedFrame received = queue[readIndex];
        RemoteAction action;
        readIndex = (uint8_t)((readIndex + 1) % QUEUE_SIZE);
        if ((uint32_t)(clockMs - received.received) > CONTROL_TIMEOUT_MS) continue;
        action = RemoteGate_Receive(&gate, &received.frame, received.received);
        if (action.stop) Mode31_RemoteStop();
        if (action.start) Mode31_RemoteStart();
        if (action.direction) Mode31_RemoteTurn(action.direction == CONTROL_LEFT ? 1 : -1);
    }
    if (RemoteGate_Expire(&gate, clockMs)) Mode31_RemoteStop();
}
