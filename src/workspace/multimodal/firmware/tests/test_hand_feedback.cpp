#include <cassert>
#include <cstdio>
#include <cstring>
#include "../esp32/MultiControlS3/GloveLogic.h"
#include "../hand_nano/hand_controller/HandWire.h"

int main() {
  // Real cross-target codecs, not sizeof(struct): a known six-servo command
  // travels from the ESP encoder to the Nano decoder without reinterpret casts.
  int16_t pose[6]={5,30,75,110,150,180};
  uint8_t control[HAND_CONTROL_SIZE]; encodeHand(0xfffe,pose,control);
  HandWire::Control decoded={};
  assert(HandWire::decode(control,sizeof(control),decoded));
  assert(decoded.sequence==0xfffe && memcmp(pose,decoded.angle,sizeof(pose))==0);
  auto sentinel=decoded; control[12]=181;
  assert(!HandWire::decode(control,sizeof(control),decoded));
  assert(memcmp(&sentinel,&decoded,sizeof(decoded))==0); // Invalid sixth angle is atomic.
  control[12]=0xff; control[13]=0xff;
  assert(!HandWire::decode(control,sizeof(control),decoded));
  assert(!HandWire::decode(control,13,decoded));
  assert(HandWire::newer(0,0xffff));
  assert(!HandWire::newer(0xffff,0));
  assert(!HandWire::newer(7,7));
  assert(!HandWire::newer(0x8000,0));

  uint16_t raw[5]={1023,0,250,777,512};
  uint8_t ack[HandWire::FeedbackSize]; HandWire::feedback(0xbeef,raw,0x35,ack);
  const uint8_t golden[13]={0xef,0xbe,0xff,3,0,0,0xfa,0,9,3,0,2,0x35};
  assert(memcmp(ack,golden,sizeof(golden))==0);
  HandFeedback result={}; assert(decodeFeedback(ack,sizeof(ack),result));
  assert(result.sequence==0xbeef && result.flags==0x35);
  assert(memcmp(result.pressureRaw,raw,sizeof(raw))==0);
  HandFeedback old=result;
  assert(!decodeFeedback(ack,5,result));
  assert(!decodeFeedback(ack,14,result));
  assert(memcmp(&old,&result,sizeof(result))==0);
  ack[11]=4; assert(!decodeFeedback(ack,13,result)); // Fifth channel range validation.
  ack[11]=2; ack[12]=0x40; assert(!decodeFeedback(ack,13,result));

  PressureCalibration cal={}; cal.tag=PRESSURE_TAG;
  for (unsigned i=0;i<5;++i) { cal.zero[i]=(uint16_t)(1000-i*30); cal.span[i]=(uint16_t)(400-i*30); }
  assert(pressureCalibrationValid(cal));
  for (unsigned i=0;i<5;++i) {
    assert(pressureDuty(cal.zero[i],cal.zero[i],cal.span[i])==0);
    assert(pressureDuty(cal.zero[i]-10,cal.zero[i],cal.span[i])==0);
    assert(pressureDuty(cal.span[i],cal.zero[i],cal.span[i])==255);
    assert(pressureDuty(0,cal.zero[i],cal.span[i])==255);
    uint8_t previous=0;
    for (int p=cal.zero[i];p>=cal.span[i];--p) {
      uint8_t next=pressureDuty((uint16_t)p,cal.zero[i],cal.span[i]); assert(next>=previous); previous=next;
    }
  }
  cal.span[4]=cal.zero[4]-29; assert(!pressureCalibrationValid(cal));
  assert(pressureDuty(0,cal.zero[4],cal.span[4])==0);
  cal.span[4]=cal.zero[4]-30; assert(pressureCalibrationValid(cal));
  assert(pressureDuty(1024,1000,400)==0);
  // All five first samples are real readings; no zero-initialized phantom squeeze.
  for (unsigned i=0;i<5;++i) {
    uint16_t first=HandWire::filter(1023,0,false);
    assert(first==1023 && pressureDuty(first,1000,400)==0);
    assert(HandWire::filter(0,first,true)==767);
  }
  int16_t safe[6]; for (unsigned i=0;i<6;++i) safe[i]=SAFE_SERVO_ANGLES[i];
  assert(poseMatchesSafe(safe)); safe[5]=0; assert(!poseMatchesSafe(safe));
  PoseCalibration poses={}; poses.tag=POSE_TAG;
  for (unsigned i=0;i<6;++i) { poses.open[i]=SAFE_SERVO_ANGLES[i]; poses.closed[i]=30; }
  assert(poseCalibrationValid(poses)==SAFE_POSE_VERIFIED);
  puts("hand: cross-target codecs, stale sequence, five pressure calibration and first-sample safety PASS");
}
