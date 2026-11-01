#ifndef REMOTE_CONTROL_H
#define REMOTE_CONTROL_H
#include <stdint.h>
void RemoteControl_Init(void);
void RemoteControl_Poll(void);
void RemoteControl_Tick(void);
void RemoteControl_Block(void);
uint8_t RemoteControl_Ready(void);
#endif
