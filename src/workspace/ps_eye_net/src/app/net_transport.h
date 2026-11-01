#ifndef Z15_NET_TRANSPORT_H
#define Z15_NET_TRANSPORT_H
#include "net_control.h"
int net_transport_init(NetControl *control);
void net_transport_poll(void);
int net_transport_peer(void);
int net_transport_send_frame(const u8 *frame,u32 sampled_ms,u32 sequence);
void net_transport_status(void);
void net_transport_stop(void);
#endif
