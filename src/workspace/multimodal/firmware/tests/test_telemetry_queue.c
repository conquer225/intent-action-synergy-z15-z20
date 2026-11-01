#include <assert.h>
#include "../stm32/Hardware/TelemetryQueue.h"
int main(void){
 TelemetryQueue q={0};uint8_t byte;unsigned n=0;
 assert(Telemetry_Offer(&q,"S,0,0,1,1\nT,200,2050,-12,35\n"));
 assert(!Telemetry_Offer(&q,"replacement\n"));
 while(Telemetry_Take(&q,&byte))++n;
 assert(n==strlen("S,0,0,1,1\nT,200,2050,-12,35\n"));
 assert(Telemetry_Offer(&q,"next\n"));return 0;
}
