#ifndef STM_TELEMETRY_H
#define STM_TELEMETRY_H
#include <stdint.h>
#include <stddef.h>
struct StmTelemetry { uint32_t time=0;uint16_t adc=0;int16_t location=0,pwm=0; };
inline bool parseTelemetry(const char *line,size_t length,StmTelemetry &row){
 if(!line || length<9 || length>47 || line[0]!='T' || line[1]!=',')return false;
 size_t pos=2;int64_t values[4]={};
 for(unsigned f=0;f<4;++f){
  bool negative=pos<length && line[pos]=='-';if(negative)++pos;
  size_t first=pos;uint64_t value=0;
  while(pos<length && line[pos]>='0' && line[pos]<='9'){
   if(pos-first>=10)return false;
   value=value*10+unsigned(line[pos++]-'0');
  }
  if(first==pos || value>4294967295ULL)return false;
  values[f]=negative?-int64_t(value):int64_t(value);
  if(f<3 && (pos==length || line[pos++]!=','))return false;
 }
 if(pos!=length || values[0]<0 || values[1]<0 || values[1]>4095 || values[2]<-32768 || values[2]>32767 || values[3]<-100 || values[3]>100)return false;
 row.time=uint32_t(values[0]);row.adc=uint16_t(values[1]);row.location=int16_t(values[2]);row.pwm=int16_t(values[3]);return true;
}
#endif
