#pragma once
#include "Arduino.h"
#include "SPI.h"
#include <cstring>
inline uint16_t receiverSequence=0;inline bool receiverSeen=false;inline uint8_t feedbackBytes[13]={};
inline uint32_t transmittedCount=0;inline uint8_t lastControlBytes[14]={};
constexpr int RF24_1MBPS=0,RF24_PA_LOW=0,RF24_CRC_16=0;
class RF24{
 bool pending=false,ack=false;uint8_t bytes[13]={};
 public:
 RF24(int,int,unsigned long){}bool begin(SPIClass*){return true;}
 void setChannel(int){}void setDataRate(int){}void setPALevel(int){}void setCRCLength(int){}void setRetries(int,int){}void setAutoAck(bool){}void enableAckPayload(){}void openWritingPipe(const uint8_t*){}void stopListening(){}
 void flush_tx(){pending=false;}void flush_rx(){ack=false;}
 void whatHappened(bool& ok,bool& failed,bool& received){ok=received=pending;failed=false;ack=pending;pending=false;}
 bool available(){return ack;}uint8_t getDynamicPayloadSize(){return 13;}
 void read(void* p,size_t n){memcpy(p,bytes,n);ack=false;}
 bool startWrite(const void* data,uint8_t n,bool){
  if(n!=14)return false;
  ++transmittedCount;memcpy(lastControlBytes,data,14);
  // Hardware sends the previously queued ACK before the receiver accepts this packet.
  memcpy(bytes,feedbackBytes,13);const uint8_t* b=(const uint8_t*)data;uint16_t seq=b[0]|uint16_t(b[1])<<8;
  uint16_t delta=uint16_t(seq-receiverSequence);
  if(!receiverSeen||(delta&&delta<0x8000)){
   receiverSeen=true;receiverSequence=seq;feedbackBytes[0]=seq;feedbackBytes[1]=seq>>8;feedbackBytes[12]=0x20;
  }
  pending=true;return true;
 }
};
