/* Runs the production Mode3.c, RemoteControl.c and PID.c with simulated I/O. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "../stm32/User/Mode3.c"
#include "../stm32/User/ControlProtocol.h"

uint8_t CurrMode = 0x31, NextMode = 0x31;
struct Menu_List ParamMenu;
uint16_t Store_Data[512];
static int16_t encoder, duty;
static uint16_t angle = 2050;
static uint8_t k4 = 1, serialError, sequence, eventId, direction;
static uint8_t incoming[2048];
static unsigned readPos, writePos;

int16_t Encoder_GetLocation(uint8_t n) { (void)n; return encoder; }
void Encoder_SetLocation(uint8_t n, int16_t value) { (void)n; encoder = value; }
void Motor_SetPWM(uint8_t n, int16_t value) { (void)n; duty = value; }
int16_t Motor_GetPWM(uint8_t n) { (void)n;return duty; }
uint16_t AD_GetValue(uint8_t n) { (void)n; return angle; }
uint8_t Key_ReadPin(uint8_t n) { return n == 4 ? k4 : 1; }
uint8_t Key_Check(uint8_t n, uint8_t e) { (void)n; (void)e; return 0; }
void Key_Clear(void) {}
void LED_ON(void) {}
void LED_OFF(void) {}
void Store_Save(void) {}
void OLED_Clear(void) {}
void OLED_Update(void) {}
void OLED_ShowString(int16_t x, int16_t y, char *s, uint8_t f) {
    (void)x; (void)y; (void)s; (void)f;
}
uint8_t Serial_ReadByte(uint8_t *b) {
    if (readPos == writePos) return 0;
    *b = incoming[readPos++ % sizeof(incoming)]; return 1;
}
uint8_t Serial_TakeRxError(void) { uint8_t e = serialError; serialError = 0; return e; }
void Serial_SendString(char *s) { (void)s; }
static char lastTelemetry[128];
uint8_t Serial_TryTelemetry(const char *s) { strcpy(lastTelemetry,s);return 1; }
void Serial_PollTelemetry(void) {}

static void enqueue(uint8_t flags, int corrupt) {
    uint8_t bytes[9]; unsigned i;
    ControlFrame f = {sequence++, flags, eventId, direction};
    Control_Encode(&f, bytes);
    if (corrupt) bytes[7] ^= 0x20;
    for (i = 0; i < 9; ++i) incoming[writePos++ % sizeof(incoming)] = bytes[i];
}
static void feed(uint8_t flags) {
    enqueue(flags, 0); Mode31_Loop(); Mode31_Tick();
}
static void wait_with_heartbeat(unsigned ms, uint8_t flags) {
    unsigned i;
    for (i = 0; i < ms; ++i) {
        if (i % 50 == 0) { enqueue(flags, 0); Mode31_Loop(); }
        Mode31_Tick();
        if (RunState == 3) assert(abs(duty) <= JOG_PWM_LIMIT);
    }
}
static void reset(void) {
    sequence = eventId = direction = 0; readPos = writePos = 0;
    encoder = 100; angle = 2050; k4 = 1; serialError = 0;
    ParamMenu.Items[0].Num = 2050; ParamMenu.Items[1].Num = 35;
    ParamMenu.Items[2].Num = 90; ParamMenu.Items[3].Num = 0;
    Mode31_Init();
}

int main(void) {
    unsigned i;
    reset(); assert(RunState == 0 && duty == 0);
    for(i=0;i<200;++i)Mode31_Tick();Mode31_Loop();
    assert(strstr(lastTelemetry,"T,200,2050,100,0\n")!=NULL);
    feed(3); feed(3); assert(RunState == 0); // High on boot cannot start.
    feed(1); feed(3); assert(RunState == 14 && duty == -35);
    feed(1); assert(RunState == 0 && duty == 0); // Release aborts swing-up.
    ++eventId; direction = CONTROL_LEFT; feed(1);
    assert(RunState == 3 && Mode31_GetTarget() == 508);
    wait_with_heartbeat(100, 1);
    assert(RunState == 3 && Mode31_GetTarget() == 508 && duty > 0);
    /* Fixture moves encoder toward the requested endpoint; test arrival stop. */
    for (i = 0; i < 204; ++i) {
        encoder += 2; wait_with_heartbeat(10, 1);
    }
    wait_with_heartbeat(160, 1);
    assert(RunState == 0 && duty == 0);
    ++eventId; direction = CONTROL_RIGHT; feed(1);
    assert(RunState == 3 && Mode31_GetTarget() == 100);
    wait_with_heartbeat(100, 1); assert(duty < 0);
    feed(3); assert(RunState == 14); // Grip interrupts standalone turn to swing up.
    ++eventId; direction = CONTROL_LEFT; feed(3);
    assert(PendingTurns == 1); // Gesture while swinging is deferred to capture.
    RunState = 1; wait_with_heartbeat(90, 3);
    assert(RunState == 2 && Mode31_GetTarget() == 408 && encoder == 0);
    ++eventId; feed(3); assert(Mode31_GetTarget() == 816);
    angle = 3500; wait_with_heartbeat(10, 3);
    assert(RunState == 0 && duty == 0 && !RemoteControl_Ready());
    feed(3); assert(RunState == 0); // No auto restart after a fall.
    angle = 2050; feed(1); feed(3); assert(RunState == 14);
    k4 = 0; Mode31_Tick(); assert(RunState == 0 && duty == 0);
    feed(1); ++eventId; feed(1); assert(RunState == 0 && duty == 0);
    k4 = 1; feed(1); feed(3); assert(RunState == 14);
    feed(0); assert(RunState == 0 && duty == 0 && !RemoteControl_Ready());

    reset(); feed(1); feed(1); ++eventId; direction = CONTROL_LEFT; feed(1);
    assert(RunState == 3);
    for (i = 0; i < 401; ++i) Mode31_Tick();
    assert(RunState == 0 && duty == 0); // Link loss stops even standalone position mode.
    feed(3); feed(3); assert(RunState == 0); // Reconnect cannot replay old high/event.
    feed(1); feed(3); assert(RunState == 14);
    serialError = 1; Mode31_Loop(); Mode31_Tick(); assert(RunState == 0 && duty == 0);

    reset(); feed(1); feed(1); ++eventId; direction = CONTROL_LEFT; feed(1);
    wait_with_heartbeat(8020, 1); // Encoder jam: heartbeat alone cannot drive indefinitely.
    assert(RunState == 0 && duty == 0);

    reset(); feed(1); feed(1); feed(3); // Valid command starts.
    for (i = 0; i < 10; ++i) {
        enqueue(3, 1); Mode31_Loop();
        { unsigned j; for (j = 0; j < 50; ++j) Mode31_Tick(); }
    }
    assert(RunState == 0 && duty == 0); // Damaged packets do not keep motors alive.
    puts("Production pendulum state/serial tests passed.");
    return 0;
}
