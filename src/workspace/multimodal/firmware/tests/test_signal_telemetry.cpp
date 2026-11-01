#include <cassert>
#include <cstdio>
#include "../esp32/MultiControlS3/SignalFrames.h"
int main() {
  SignalFrames frames; frames.begin(123,0xfffff000u);
  for (int n=0;n<10;++n) frames.sample(uint32_t(0xfffff000u+2000u*(n+1)),uint16_t(2000+n),true);
  char line[1024]; assert(frames.take(line,sizeof(line)));
  JsonDocument doc; assert(!deserializeJson(doc,line));
  assert(doc["type"]=="raw" && doc["samples"].size()==10 && doc["time_us"].as<uint64_t>()==2000);
  assert(doc["samples"][9].as<int>()==2009 && doc["dt_us"][1].as<int>()==2000);
  frames.contact(uint32_t(0xfffff000u+20500u),false,false,0);
  while(frames.take(line,sizeof(line))) {}
  for(int n=0;n<60;++n) frames.sample(uint32_t(0xfffff000u+22000u+2000u*n),1000,false);
  assert(frames.dropped()>0); frames.contact(0x00020000, true, true,200);
  bool sawEvent=false; while(frames.take(line,sizeof(line))) { deserializeJson(doc,line); if(doc["type"]=="contact") sawEvent=true; }
  assert(sawEvent);
  frames.contact(0x00020100,true,true,200); assert(!frames.take(line,sizeof(line)));
  frames.status(0x00020200,true,true,false,true);
  assert(frames.take(line,sizeof(line))); deserializeJson(doc,line);
  assert(doc["imu"].as<bool>() && !doc["worn"].as<bool>());
  puts("Signal frames: wrap, raw samples, bounded congestion, unique contact edge PASS");
}
