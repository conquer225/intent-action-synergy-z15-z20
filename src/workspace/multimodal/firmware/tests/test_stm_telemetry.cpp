#include <cassert>
#include <string>
#include "../esp32c3/PendulumBridgeC3/StmTelemetry.h"
int main(){
 StmTelemetry row;
 const std::string line="T,4294967295,2050,-12,35";
 assert(parseTelemetry(line.data(),line.size(),row));
 assert(row.time==4294967295u && row.adc==2050 && row.location==-12 && row.pwm==35);
 const std::string bad="T,4294967296,2050,-12,35";
 assert(!parseTelemetry(bad.data(),bad.size(),row));
 const std::string extra="T,1,4096,0,0";assert(!parseTelemetry(extra.data(),extra.size(),row));
 const std::string suffix="T,1,2,3,4extra";assert(!parseTelemetry(suffix.data(),suffix.size(),row));
}
