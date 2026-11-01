#pragma once
#include <ArduinoJson.h>
#include <stdint.h>
#include <string.h>
#include <math.h>

// Public producer/consumer seam. No allocation or socket work per ADC sample.
class SignalFrames {
 public:
  void begin(uint32_t id,uint32_t now) { session=id?id:1; lastUs=lastSampleUs=now; elapsed=0; used=head=count=0; sequence=index=lost=event=0; contactSeen=false; }
  void sample(uint32_t now,uint16_t adc,bool worn) {
    uint32_t dt=now-lastSampleUs; lastSampleUs=now; advance(now); if(!used) { first=index; blockTime=elapsed; mask=0; valid=true; }
    raw[used]=adc; intervals[used]=dt; if(worn) mask|=uint16_t(1u<<used);
    valid=valid && dt>0 && dt<=6000 && adc<=4095; ++index;
    if(++used==10) {
      JsonDocument d; envelope(d,"raw"); d["time_us"]=blockTime; d["sample_index"]=first;
      d["sample_rate_hz"]=500; d["wear_mask"]=mask; d["valid"]=valid;
      JsonArray a=d["samples"].to<JsonArray>(),b=d["dt_us"].to<JsonArray>();
      for(unsigned n=0;n<10;++n) { a.add(raw[n]); b.add(intervals[n]); }
      enqueue(d,false); used=0;
    }
  }
  void contact(uint32_t now,bool pressed,bool armed,float strength) {
    advance(now);
    if(contactSeen && pressed==lastContact && armed==lastArmed) return;
    contactSeen=true; lastContact=pressed; lastArmed=armed;
    JsonDocument d; envelope(d,"contact"); d["event_id"]=++event; d["pressed"]=pressed;
    d["armed"]=armed; d["strength"]=isfinite(strength)?strength:0; d["valid"]=isfinite(strength);
    enqueue(d,true);
  }
  void status(uint32_t now, bool pressed,bool armed,bool worn,bool imu) {
    advance(now); JsonDocument d; envelope(d,"signal_status"); d["pressed"]=pressed;
    d["armed"]=armed; d["worn"]=worn; d["imu"]=imu; d["sample_index"]=index; enqueue(d,true);
  }
  bool take(char *output,size_t capacity) {
    if(!count || strlen(lines[head])+1>capacity) return false;
    memcpy(output,lines[head],strlen(lines[head])+1); head=(head+1)%4; --count; return true;
  }
  uint32_t dropped() const { return lost; }
  void discard() { lost+=count; head=count=used=0; }
 private:
  char lines[4][768]={}; unsigned head=0,count=0,used=0;
  uint16_t raw[10]={},mask=0; uint32_t intervals[10]={};
  uint32_t session=1,lastUs=0,lastSampleUs=0,sequence=0,index=0,first=0,lost=0,event=0;
  uint64_t elapsed=0,blockTime=0; bool valid=true,contactSeen=false,lastContact=false,lastArmed=false;
  uint32_t advance(uint32_t now) { uint32_t dt=now-lastUs; elapsed+=dt; lastUs=now; return dt; }
  void envelope(JsonDocument &d,const char *type) { d["v"]=1; d["type"]=type; d["session"]=session; d["seq"]=++sequence; d["time_us"]=elapsed; d["dropped"]=lost; }
  void enqueue(JsonDocument &d,bool priority) {
    if(count==4) { if(!priority) { ++lost; return; } lost+=count; head=count=0; }
    d["dropped"]=lost; size_t bytes=measureJson(d);
    if(bytes+2>sizeof(lines[0])) { ++lost; return; }
    char *line=lines[(head+count)%4]; serializeJson(d,line,sizeof(lines[0])); line[bytes]='\n'; line[bytes+1]=0; ++count;
  }
};
