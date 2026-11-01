#ifndef __MODE3_H
#define __MODE3_H

/* 1: no OLED; boot directly into the inverted pendulum, start with K1. */
#define PENDULUM_HEADLESS 1

void Mode30_Init(void);

void Mode31_SaveParam(void);
void Mode31_LoadParam(void);
uint8_t Mode31_StoredParamValid(void);
void Mode31_Init(void);
void Mode31_Loop(void);
void Mode31_Exit(void);
void Mode31_Tick(void);
void Mode31_RemoteStart(void);
void Mode31_RemoteStop(void);
void Mode31_RemoteTurn(int8_t Direction);
uint8_t Mode31_GetRunState(void);
int16_t Mode31_GetTarget(void);

#endif
