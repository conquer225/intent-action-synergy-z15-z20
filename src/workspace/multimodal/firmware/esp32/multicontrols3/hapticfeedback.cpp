#include "HapticFeedback.h"
#include <string.h>

bool HapticFeedback::begin() {
  // Set every gate low BEFORE attaching any PWM peripheral.
  for (uint8_t i=0;i<5;++i) { pinMode(MOTOR_PINS[i],OUTPUT); digitalWrite(MOTOR_PINS[i],LOW); }
  ready=true;
  for (uint8_t i=0;i<5;++i) {
    attached[i]=ledcAttachChannel(MOTOR_PINS[i],1000,8,i);
    if (!attached[i]) ready=false;
  }
  stop();
  storageReady=prefs.begin("haptic-s3",false);
  if (storageReady && prefs.getBytesLength("pressure-v2")==sizeof(cal)) {
    prefs.getBytes("pressure-v2",&cal,sizeof(cal)); calibrated=pressureCalibrationValid(cal);
  }
  if (calibrated) { draft=cal; zeroMask=spanMask=0x1f; }
  return ready;
}
void HapticFeedback::stop() {
  for (uint8_t i=0;i<5;++i) {
    duty[i]=0;
    if (released[i]) continue;
    if (attached[i]) ledcWrite(MOTOR_PINS[i],0);
    else digitalWrite(MOTOR_PINS[i],LOW);
  }
}
void HapticFeedback::releasePinForInput(int pin) {
  stop();
  for (uint8_t i=0;i<5;++i) if (MOTOR_PINS[i]==pin) {
    if (attached[i]) ledcDetach(pin);
    attached[i]=false; released[i]=true; ready=false;
  }
  pinMode(pin,INPUT);
}
void HapticFeedback::tick(bool enabled,bool fresh,const HandFeedback &feedback) {
  if (!ready || !enabled || !fresh || !calibrated || calibrating || !(feedback.flags&0x20u)) { stop(); return; }
  for (uint8_t i=0;i<5;++i) {
    duty[i]=pressureDuty(feedback.pressureRaw[i],cal.zero[i],cal.span[i]);
    ledcWrite(MOTOR_PINS[i],duty[i]);
  }
}
void HapticFeedback::show() {
  Serial.printf("# PRESSURE_CAL_VALID:%u PWM_READY:%u ZERO_MASK:%u SPAN_MASK:%u\n",
                calibrated,ready,zeroMask,spanMask);
  for (uint8_t i=0;i<5;++i)
    Serial.printf("# PRESSURE%u zero:%u span:%u duty:%u\n",i+1,draft.zero[i],draft.span[i],duty[i]);
}
bool HapticFeedback::command(char *line,bool fresh,const HandFeedback &feedback) {
  if (strncmp(line,"pressure ",9)!=0) return false;
  stop();
  const char *verb=line+9;
  if (strcmp(verb,"show")==0) { show(); return true; }
  if (strcmp(verb,"save")==0) {
    if (zeroMask!=0x1f || spanMask!=0x1f || !pressureCalibrationValid(draft)) {
      Serial.println("ERROR,PRESSURE_CAPTURE_ALL5_ZERO_SPAN_AT_LEAST_30"); show(); return true;
    }
    if (!storageReady || prefs.putBytes("pressure-v2",&draft,sizeof(draft))!=sizeof(draft)) {
      Serial.println("ERROR,PRESSURE_STORAGE_FAILED"); return true;
    }
    cal=draft; calibrated=true; calibrating=false; Serial.println("ACK,PRESSURE_SAVED"); return true;
  }
  bool zero=strncmp(verb,"zero",4)==0, span=strncmp(verb,"span",4)==0;
  if (!zero && !span) { Serial.println("ERROR,PRESSURE_COMMAND"); return true; }
  uint8_t mask=0x1f;
  if (verb[4]!=0) {
    if (verb[4]!=' ' || verb[5]<'1' || verb[5]>'5' || verb[6]!=0) {
      Serial.println("ERROR,PRESSURE_CHANNEL_1_TO_5"); return true;
    }
    mask=1u<<(verb[5]-'1');
  }
  if (!fresh) { Serial.println("ERROR,PRESSURE_FEEDBACK_STALE"); return true; }
  if (span) for (uint8_t i=0;i<5;++i) if (mask&(1u<<i)) {
    if (!(zeroMask&(1u<<i))) { Serial.println("ERROR,PRESSURE_CAPTURE_ZERO_FIRST"); return true; }
    if (!pressureChannelValid(draft.zero[i],feedback.pressureRaw[i])) {
      Serial.println("ERROR,PRESSURE_SPAN_MUST_BE_30_BELOW_ZERO"); return true;
    }
  }
  calibrating=true;
  draft.tag=PRESSURE_TAG;
  for (uint8_t i=0;i<5;++i) if (mask&(1u<<i)) {
    if (zero) {
      draft.zero[i]=feedback.pressureRaw[i]; zeroMask|=(1u<<i); spanMask&=~(1u<<i);
    } else {
      if (!(zeroMask&(1u<<i))) {
        Serial.println("ERROR,PRESSURE_CAPTURE_ZERO_FIRST"); return true;
      }
      if (!pressureChannelValid(draft.zero[i],feedback.pressureRaw[i])) {
        Serial.println("ERROR,PRESSURE_SPAN_MUST_BE_30_BELOW_ZERO"); return true;
      }
      draft.span[i]=feedback.pressureRaw[i]; spanMask|=(1u<<i);
    }
  }
  Serial.printf("ACK,PRESSURE_%s_CAPTURED,%u\n",zero?"ZERO":"SPAN",mask);
  show(); return true;
}
