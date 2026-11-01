#include "GloveController.h"
#include "GloveInputConfig.h"
#include <string.h>
#include <stdlib.h>

// Keep EMG/wear, I2C and native USB pins untouched during input discovery.
static constexpr int LOCATE_PINS[]={3,8};

static bool parseAngles(char *text,int16_t *out) {
  int16_t parsed[6]={}; char *cursor=text;
  for (uint8_t i=0;i<6;++i) {
    if (!cursor || !*cursor) return false;
    char *comma=strchr(cursor,',');
    if ((i<5 && !comma) || (i==5 && comma)) return false;
    if (comma) *comma=0;
    for (const char *p=cursor;*p;++p) if (*p<'0'||*p>'9') return false;
    char *end=nullptr; long value=strtol(cursor,&end,10);
    if (*end || value<0 || value>180) return false;
    parsed[i]=(int16_t)value; cursor=comma?comma+1:nullptr;
  }
  memcpy(out,parsed,sizeof(parsed)); return true;
}
const char *GloveController::modeName() const {
  return mode==HandMode::GLOVE?"GLOVE":mode==HandMode::EMG?"EMG":"NETWORK";
}
void GloveController::openAngles() {
  for (uint8_t i=0;i<6;++i) angles[i]=posesReady?poses.open[i]:SAFE_SERVO_ANGLES[i];
}
void GloveController::syncHapticStatus() {
  pressureCalibrated=haptics.calibrated;
  memcpy(motorDuty,haptics.duty,sizeof(motorDuty));
}
void GloveController::begin() {
  for (uint8_t i=0;i<POT_COUNT;++i) {
    pinMode(POT_PINS[i],INPUT); analogSetPinAttenuation(POT_PINS[i],ADC_11db);
  }
  storageReady=prefs.begin("glove-s3",false);
  if (storageReady && prefs.getBytesLength("cal-v1")==sizeof(calibration)) {
    prefs.getBytes("cal-v1",&calibration,sizeof(calibration)); calibrated=calibrationValid(calibration);
  }
  if (storageReady && prefs.getBytesLength("poses-v2")==sizeof(poses)) {
    prefs.getBytes("poses-v2",&poses,sizeof(poses)); posesReady=poseCalibrationValid(poses);
  }
  if (posesReady) { poseDraft=poses; poseOpenCaptured=poseClosedCaptured=true; }
  openAngles(); enabled=stopping=false;
  bool pwmReady=haptics.begin(); syncHapticStatus();
  Serial.printf("# RF_READY:%u CAL_VALID:%u POSES_READY:%u SAFE_CONFIG:%u PWM_READY:%u HAND_ENABLED:0\n",
                radio.begin(),calibrated,posesReady,SAFE_POSE_VERIFIED,pwmReady);
}
void GloveController::stop() {
  enabled=false; pressurePolling=false; gripArmed=false; gripClosed=false;
  radio.cancel(); openAngles();
  stopping=posesReady && SAFE_POSE_VERIFIED && radio.ready;
  stopStartedMs=millis(); haptics.stop(); syncHapticStatus();
}
void GloveController::setMode(HandMode value) {
  if (mode==value) return;
  stop(); mode=value; pcMode=value==HandMode::NETWORK; gripValid=false;
  openAngles();
}
bool GloveController::enable() {
  if (locating) return false;
  if (!radio.ready || !posesReady || !SAFE_POSE_VERIFIED || captureKind) return false;
  if (mode==HandMode::GLOVE) {
    if (potFrames<32) return false;
    if (mapping==GloveMapping::CALIBRATED && !calibrated) return false;
    if (mapping==GloveMapping::DIRECT && !calibrationValid(DIRECT_GLOVE_RANGE)) return false;
  }
  if (!radio.actuatorReady()) {
    stop(); pressurePolling=true; stopping=false; openAngles();
    // Probe using OPEN only. The operator retries ENABLE after a verified ACK.
    return false;
  }
  radio.cancel(); stopping=false; pressurePolling=false; enabled=true;
  enabledSinceMs=millis();
  if (mode==HandMode::EMG) { gripArmed=false; gripClosed=false; openAngles(); }
  else if (mode==HandMode::GLOVE) updateAngles();
  else openAngles(); // Re-enabling NETWORK always starts from the neutral pose.
  return true;
}
void GloveController::tick() {
  if (enabled) {
    // A fresh feedback saying the Nano configuration is unverified cancels movement.
    if ((radio.pressureFresh() && !(radio.feedback.flags&0x20u)) ||
        (uint32_t(millis()-enabledSinceMs)>=300 && (!radio.ackFresh() || !radio.actuatorReady()))) stop();
  }
  if (stopping && (uint32_t)(millis()-stopStartedMs)>=100) {
    stopping=false; radio.cancel();
  }
  // Even a fresh USB/network target received while OFF cannot replace the
  // dedicated safe-open retry/calibration frames.
  const int16_t *output=(stopping||pressurePolling)?poses.open:angles;
  radio.tick(enabled||stopping||pressurePolling,output);
  haptics.tick(enabled,radio.pressureFresh(),radio.feedback);
  syncHapticStatus();
}
void GloveController::setGrip(bool gripped,bool valid) {
  gripValid=valid;
  if (mode!=HandMode::EMG || !enabled) return;
  if (!valid) { stop(); return; }
  if (!gripped) { gripArmed=true; gripClosed=false; preset(false); }
  else if (gripArmed && !gripClosed) { gripClosed=true; preset(true); }
}
bool GloveController::setNetworkPose(const int16_t *target) {
  if (mode!=HandMode::NETWORK || !posesReady || !anglesValid(target)) return false;
  memcpy(angles,target,sizeof(angles)); return true;
}
bool GloveController::preset(bool closed) {
  if (!posesReady || mode==HandMode::GLOVE) return false;
  memcpy(angles,closed?poses.closed:poses.open,sizeof(angles)); return true;
}
bool GloveController::capturePose(bool closed,const int16_t *target) {
  stop();
  if (!anglesValid(target)) return false;
  if (!closed && (!SAFE_POSE_VERIFIED || !poseMatchesSafe(target))) return false;
  poseDraft.tag=POSE_TAG;
  memcpy(closed?poseDraft.closed:poseDraft.open,target,sizeof(angles));
  if (closed) poseClosedCaptured=true; else poseOpenCaptured=true;
  return true;
}
bool GloveController::savePoses() {
  stop();
  if (!poseOpenCaptured || !poseClosedCaptured || !poseCalibrationValid(poseDraft)) return false;
  if (!storageReady || prefs.putBytes("poses-v2",&poseDraft,sizeof(poseDraft))!=sizeof(poseDraft)) return false;
  poses=poseDraft; posesReady=true; openAngles(); return true;
}
void GloveController::updateAngles() {
  if (mode!=HandMode::GLOVE) return;
  bool fixed=mapping!=GloveMapping::CALIBRATED;
  for (uint8_t i=0;i<POT_COUNT;++i) {
    bool active=fixed?(DIRECT_GLOVE_CHANNELS&(1u<<i))!=0:calibrated;
    uint8_t input=fixed?DIRECT_GLOVE_INPUT_INDEX[i]:i;
    if (!active || !posesReady) angles[i]=SAFE_SERVO_ANGLES[i];
    else if (mapping==GloveMapping::NANO) angles[i]=nanoGloveAngle(filtered[input],i);
    else angles[i]=potAngle(filtered[input],i,fixed?DIRECT_GLOVE_RANGE:calibration,poses);
  }
}
void GloveController::sample() {
  uint32_t now=micros(); if ((uint32_t)(now-lastPotUs)<1000) return; lastPotUs=now;
  uint8_t i=nextPot; raw[i]=(uint16_t)analogRead(POT_PINS[i]);
  filtered[i]=seen[i]?(uint16_t)((3UL*filtered[i]+raw[i])/4):raw[i];
  if (seen[i]<32) ++seen[i]; nextPot=(i+1)%POT_COUNT;
  if (nextPot) return;
  if (potFrames<1000000) ++potFrames;
  if (captureKind) {
    for (uint8_t p=0;p<POT_COUNT;++p) captureSum[p]+=raw[p];
    if (++captureFrames==32) {
      uint16_t *endpoint=captureKind==1?draft.open:draft.closed;
      for (uint8_t p=0;p<POT_COUNT;++p) endpoint[p]=captureSum[p]/32;
      if (captureKind==1) openCaptured=true; else closedCaptured=true;
      Serial.println(captureKind==1?"ACK,OPEN_CAPTURED":"ACK,CLOSE_CAPTURED");
      captureKind=0; showCalibration();
    }
  }
  if (!stopping && !pressurePolling) updateAngles(); // Keep safe-open during retries/calibration.
}
void GloveController::startCapture(uint8_t kind,void (*stopPendulum)()) {
  stop(); stopPendulum(); captureKind=kind; captureFrames=0;
  memset(captureSum,0,sizeof(captureSum));
  if (kind==1) { draft={}; draft.tag=CAL_TAG; openCaptured=closedCaptured=false; }
  else closedCaptured=false;
  Serial.println(kind==1?"# Hold OPEN until OPEN_CAPTURED (~0.2 seconds).":"# Hold CLOSED until CLOSE_CAPTURED (~0.2 seconds).");
}
void GloveController::showCalibration() {
  Serial.printf("# GLOVE_MAPPING:%s CHANNEL_MASK:%u\n",mappingName(),
                mapping!=GloveMapping::CALIBRATED?DIRECT_GLOVE_CHANNELS:0x3f);
  Serial.printf("# CAL_VALID:%u DRAFT_OPEN:%u DRAFT_CLOSED:%u POSES_READY:%u SAFE_CONFIG:%u\n",
                calibrated,openCaptured,closedCaptured,posesReady,SAFE_POSE_VERIFIED);
  const PotCalibration &display=openCaptured?draft:calibration;
  for (uint8_t i=0;i<POT_COUNT;++i)
    Serial.printf("# P%u GPIO%d raw:%u open:%u closed:%u angle:%d SAFE:%u POSE_OPEN:%d POSE_CLOSE:%d\n",
      i+1,POT_PINS[i],raw[i],display.open[i],display.closed[i],angles[i],SAFE_SERVO_ANGLES[i],poseDraft.open[i],poseDraft.closed[i]);
}
bool GloveController::pcCommand(char *line) {
  if (strncmp(line,"CMD_V1,",7)!=0) return false;
  if (strcmp(line,"CMD_V1,MODE,PC")==0) {
    setMode(HandMode::NETWORK); stop(); Serial.println("ACK_V1,MODE,PC"); return true;
  }
  if (strcmp(line,"CMD_V1,MODE,GLOVE")==0) {
    setMode(HandMode::GLOVE); stop(); Serial.println("ACK_V1,MODE,GLOVE"); return true;
  }
  if (strncmp(line,"CMD_V1,POSE,",12)==0) {
    int16_t parsed[6];
    if (!parseAngles(line+12,parsed) || !setNetworkPose(parsed)) Serial.println("ACK_V1,ERROR,NETWORK_MODE_VERIFIED_POSES_AND_ANGLES_REQUIRED");
    else Serial.println("ACK_V1,POSE,OK");
    return true;
  }
  Serial.println("ACK_V1,ERROR,UNKNOWN_COMMAND"); return true;
}
bool GloveController::command(char *line,void (*stopPendulum)()) {
  if (strcmp(line,"pot locate")==0) {
    stop(); locating=true;
    // Release haptic PWM owners before using any candidate as an ADC input.
    for (int pin:LOCATE_PINS) {
      haptics.releasePinForInput(pin);
      analogSetPinAttenuation(pin,ADC_11db);
    }
    Serial.println("ACK,POT_LOCATE,HAND_OFF,GPIO3_GPIO8,RESTART_TO_EXIT");
    return true;
  }
  if (pcCommand(line)) return true;
  if (strncmp(line,"hand mode ",10)==0) {
    const char *value=line+10;
    if (strcmp(value,"glove")==0) setMode(HandMode::GLOVE);
    else if (strcmp(value,"emg")==0) setMode(HandMode::EMG);
    else if (strcmp(value,"network")==0) setMode(HandMode::NETWORK);
    else { Serial.println("ERROR,HAND_MODE_glove_emg_network"); return true; }
    stop(); Serial.printf("ACK,HAND_MODE,%s\n",modeName()); return true;
  }
  if (strcmp(line,"hand off")==0) { stop(); Serial.println("ACK,HAND_OFF"); return true; }
  if (strcmp(line,"hand on")==0) {
    Serial.println(enable()?"ACK,HAND_ON":"ERROR,HAND_NEEDS_RF_VERIFIED_POSES_AND_READY_GLOVE_INPUT"); return true;
  }
  if (strncmp(line,"pose ",5)==0) {
    if (strcmp(line,"pose show")==0) { showCalibration(); return true; }
    if (strcmp(line,"pose save")==0) {
      Serial.println(savePoses()?"ACK,POSES_SAVED":"ERROR,POSE_SAVE_REQUIRES_VERIFIED_SAFE_OPEN_AND_CLOSED"); return true;
    }
    bool closed=strncmp(line,"pose close ",11)==0;
    bool opened=strncmp(line,"pose open ",10)==0;
    int16_t parsed[6];
    if ((!closed&&!opened) || !parseAngles(line+(closed?11:10),parsed)) {
      Serial.println("ERROR,POSE_open_OR_close_SIX_ANGLES"); return true;
    }
    Serial.println(capturePose(closed,parsed)?"ACK,POSE_CAPTURED":"ERROR,OPEN_MUST_MATCH_VERIFIED_HandConfig_h_EDIT_BOTH_AND_REFLASH"); return true;
  }
  if (strncmp(line,"pressure ",9)==0) {
    if (strcmp(line,"pressure start")==0) {
      stop();
      if (!posesReady || !SAFE_POSE_VERIFIED || !radio.ready) {
        Serial.println("ERROR,PRESSURE_CAL_NEEDS_RF_VERIFIED_OPEN_POSE_FIRST"); return true;
      }
      pressurePolling=true; stopping=false; openAngles();
      Serial.println("ACK,PRESSURE_POLL_OPEN_ONLY_MOTORS_OFF"); return true;
    }
    // Enter a non-moving calibration poll mode: OPEN only, no haptic output.
    bool fresh=radio.pressureFresh(); HandFeedback snapshot=radio.feedback;
    bool capture=strncmp(line,"pressure zero",13)==0 || strncmp(line,"pressure span",13)==0;
    if (capture) {
      stop();
      if (!posesReady || !SAFE_POSE_VERIFIED) {
        Serial.println("ERROR,PRESSURE_CAL_NEEDS_VERIFIED_OPEN_POSE_FIRST"); return true;
      }
      pressurePolling=true; stopping=false; openAngles();
    }
    haptics.command(line,fresh,snapshot);
    if (strcmp(line,"pressure save")==0 && !haptics.calibrating) stop();
    syncHapticStatus(); return true;
  }
  if (strcmp(line,"rf")==0) {
    stop(); stopPendulum(); Serial.printf("ACK,RF_READY,%u\n",radio.begin()); return true;
  }
  const char *pot=line;
  if (strncmp(line,"pot ",4)==0) pot=line+4;
  if (strcmp(line,"pot direct")==0 || strcmp(line,"pot calibrated")==0 || strcmp(line,"pot nano")==0) {
    stop(); setMode(HandMode::GLOVE);
    mapping=strcmp(pot,"nano")==0?GloveMapping::NANO:
            strcmp(pot,"direct")==0?GloveMapping::DIRECT:GloveMapping::CALIBRATED;
    Serial.printf("ACK,GLOVE_MAPPING,%s,OFF,CHANNEL_MASK,%u\n",mappingName(),
                  mapping!=GloveMapping::CALIBRATED?DIRECT_GLOVE_CHANNELS:0x3f);
    return true;
  }
  if (strcmp(pot,"show")==0) { showCalibration(); return true; }
  if (strcmp(pot,"open")==0 || strcmp(pot,"close")==0) {
    if (captureKind) Serial.println("ERROR,CAPTURE_IN_PROGRESS");
    else if (potFrames<32) Serial.println("ERROR,WAIT_FOR_POT_SAMPLES");
    else if (strcmp(pot,"close")==0 && !openCaptured) Serial.println("ERROR,SEND_pot_open_FIRST");
    else startCapture(strcmp(pot,"open")==0?1:2,stopPendulum);
    return true;
  }
  if (strcmp(pot,"save")==0) {
    stop(); stopPendulum();
    if (captureKind || !openCaptured || !closedCaptured || !calibrationValid(draft)) {
      Serial.println("ERROR,CAL_CAPTURE_BOTH_SPAN_AT_LEAST_80"); showCalibration(); return true;
    }
    if (!storageReady || prefs.putBytes("cal-v1",&draft,sizeof(draft))!=sizeof(draft)) {
      Serial.println("ERROR,CAL_STORAGE_FAILED"); return true;
    }
    calibration=draft; calibrated=true; updateAngles(); Serial.println("ACK,CAL_SAVED"); return true;
  }
  return false;
}
void GloveController::printPots() {
  for (uint8_t i=0;i<POT_COUNT;++i) { if (i) Serial.print('\t'); Serial.printf("p%u:%u",i+1,raw[i]); }
  if (locating) for (int pin:LOCATE_PINS) Serial.printf("\tprobe%d:%d",pin,analogRead(pin));
  Serial.println();
}
void GloveController::printTelemetry() {
  Serial.printf("TELEM_V3,%u,%u,%s",radio.sequence,radio.feedback.sequence,modeName());
  for (uint8_t i=0;i<POT_COUNT;++i) Serial.printf(",%d",angles[i]);
  for (uint8_t i=0;i<5;++i) Serial.printf(",%u",radio.feedback.pressureRaw[i]);
  for (uint8_t i=0;i<5;++i) Serial.printf(",%u",motorDuty[i]);
  Serial.printf(",%u,%u,%u,%u\n",radio.feedback.flags&0x1fu,enabled&&radio.ackFresh(),radio.pressureFresh(),radio.actuatorReady());
}
