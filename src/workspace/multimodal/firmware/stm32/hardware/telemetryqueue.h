#ifndef TELEMETRY_QUEUE_H
#define TELEMETRY_QUEUE_H
#include <stdint.h>
#include <string.h>
typedef struct { uint8_t bytes[192]; uint16_t used,read; } TelemetryQueue;
static uint8_t Telemetry_Offer(TelemetryQueue *q,const char *text) {
    size_t n=strlen(text);
    if(q->used!=q->read || n>sizeof(q->bytes))return 0;
    memcpy(q->bytes,text,n);q->used=(uint16_t)n;q->read=0;return 1;
}
static uint8_t Telemetry_Take(TelemetryQueue *q,uint8_t *out) {
    if(q->used==q->read)return 0;
    *out=q->bytes[q->read++];return 1;
}
#endif
