#include <winsock2.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#define MULTICONTROL_AUTO_START 0 // Exercise the retained manual commissioning workflow.
#include "../esp32/MultiControlS3/MultiControlS3.ino"
using namespace pendulum_bridge;
GatewaySession gateway;
bool bridgeAlive=true, stmReporting=true;
uint8_t reportedStmState=0, reportedStmBlocked=0;
size_t udpRead=0;
std::vector<ControlFrame> uartFrames;
static void pumpGateway() {
  gateway.expire(millis());
  while(udpRead<WiFiUDP::outgoing.size()) {
    auto packet=WiFiUDP::outgoing[udpRead++];
    if(!bridgeAlive) continue;
    Message msg; assert(decode(packet.bytes.data(),packet.bytes.size(),msg));
    auto a=gateway.receive(msg,uint32_t(WiFi.localIP()),PORT,millis(),0xabcdef);
    if(a.serial) { uartFrames.push_back(a.output); reportedStmBlocked=(a.output.flags&CONTROL_VALID)?0:1; if(reportedStmBlocked) reportedStmState=0; }
    if(a.reply) {
      StmStatus s; s.fresh=stmReporting; s.report=uint32_t(uartFrames.size()); s.age=0; s.linked=1; s.blocked=reportedStmBlocked; s.state=reportedStmState;
      if(a.response.type==ACK) setStatus(a.response,s);
      BridgeFakeDatagram reply; reply.ip=uint32_t(IPAddress(10,0,0,10)); reply.port=PORT; reply.bytes.resize(WIRE_SIZE);
      encode(a.response,reply.bytes.data()); WiFiUDP::incoming.push_back(reply);
    }
  }
}
static void runFor(unsigned ms) {
  uint64_t until=fakeUs+1000ULL*ms;
  while(fakeUs<until) { fakeUs+=200; loop(); pumpGateway(); }
}
static void command(const char *text) { Serial.feed(text); Serial.feed("\n"); runFor(20); }
static SOCKET connectPc(unsigned port=9000) {
  SOCKET sock=socket(AF_INET,SOCK_STREAM,0); assert(sock!=INVALID_SOCKET);
  sockaddr_in addr={}; addr.sin_family=AF_INET; addr.sin_port=htons(uint16_t(port)); addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
  assert(connect(sock,reinterpret_cast<sockaddr*>(&addr),sizeof(addr))==0);
  unsigned long on=1; ioctlsocket(sock,FIONBIO,&on); runFor(1); return sock;
}
static JsonDocument ask(SOCKET sock,const char *source,unsigned seq,const char *device,const char *action,const char *extra="") {
  char line[1024]; snprintf(line,sizeof(line),"{\"v\":1,\"source\":\"%s\",\"seq\":%u,\"device\":\"%s\",\"action\":\"%s\"%s}\n",source,seq,device,action,extra);
  assert(send(sock,line,int(strlen(line)),0)==int(strlen(line)));
  std::string received;
  for(int attempt=0;attempt<40;++attempt) {
    runFor(1); Sleep(1);
    char b[4096]; int n=recv(sock,b,sizeof(b),0); if(n>0) received.append(b,n);
    size_t end;
    while((end=received.find('\n'))!=std::string::npos) {
      std::string frame=received.substr(0,end); received.erase(0,end+1);
      JsonDocument doc; assert(!deserializeJson(doc,frame));
      if(doc["seq"].is<unsigned>() && doc["seq"].as<unsigned>()==seq) return doc;
    }
  }
  assert(false && "missing production TCP ACK"); return JsonDocument();
}
int main() {
  gateway.begin(0); setup(); WiFi.state=WL_CONNECTED; runFor(500);
  assert(Wire.sda==11 && Wire.scl==12);
  assert(SPI.sck==40 && SPI.miso==38 && SPI.mosi==39 && SPI.csn==41);
  assert(!pendulumEnabled && !glove.enabled && !glove.calibrated);
  assert(imuReady && wearNow && grip.armed && pendulumLink.linked());
  for(auto f:uartFrames) assert(!f.flags);
  // Actual read-only 9010 TCP stream, complete JSON framing and consumer isolation.
  SOCKET stream=connectPc(9010);std::string signalBytes;
  for(int attempt=0;attempt<100 && signalBytes.find('\n')==std::string::npos;++attempt) {
    runFor(1);Sleep(1);char block[4096];int n=recv(stream,block,sizeof(block),0);
    if(n>0)signalBytes.append(block,n);
  }
  assert(signalBytes.find('\n')!=std::string::npos);
  JsonDocument rawSignal;assert(!deserializeJson(rawSignal,signalBytes.substr(0,signalBytes.find('\n'))));
  assert(rawSignal["v"].as<int>()==1 && rawSignal["type"].as<std::string>()=="raw");
  assert(rawSignal["samples"].size()==10 && rawSignal["dt_us"].size()==10);
  unsigned slowReads=fakeEmgReads;uint32_t slowGaps=emgGaps;runFor(1000);
  assert(fakeEmgReads-slowReads>=490 && emgGaps==slowGaps && pendulumLink.linked());
  assert(send(stream,"command\n",8,0)==8);runFor(10);
  assert(!glove.enabled && !pendulumEnabled);closesocket(stream);
  // An attached USB host that stops reading cannot starve TCP heartbeats,
  // EMG sampling or bridge maintenance. No motion is enabled in this case.
  Serial.txFree=0;
  unsigned usbReadsBefore=fakeEmgReads, usbStallsBefore=Serial.stalledWrites;
  uint32_t usbGapsBefore=emgGaps;
  size_t usbOutputBefore=Serial.output.size();
  SOCKET usbBlockedPc=connectPc();
  assert(ask(usbBlockedPc,"brain",1,"all","hello")["ok"].as<bool>());
  for(unsigned seq=2;seq<=11;++seq) {
    runFor(100);
    assert(ask(usbBlockedPc,"brain",seq,"all","heartbeat")["ok"].as<bool>());
  }
  assert(fakeEmgReads-usbReadsBefore>=490 && emgGaps==usbGapsBefore);
  assert(Serial.stalledWrites==usbStallsBefore && Serial.output.size()==usbOutputBefore);
  assert(pendulumLink.linked() && pendulumLink.stmFresh(millis()));
  closesocket(usbBlockedPc); runFor(10); Serial.txFree=2048;
  SOCKET config=connectPc();
  assert(ask(config,"pc",1,"all","hello")["ok"].as<bool>());
  assert(ask(config,"pc",2,"hand","input",",\"input\":\"contact\"")["ok"].as<bool>());
  assert(handEmgInput==HandEmgInput::CONTACT && !glove.enabled);
  assert(ask(config,"pc",3,"pendulum","mode",",\"mode\":\"tilt_test\"")["ok"].as<bool>());
  assert(pendulumMode==PendulumMode::TILT_TEST && !pendulumEnabled);
  assert(!ask(config,"pc",4,"pendulum","enable")["ok"].as<bool>());
  assert(ask(config,"pc",5,"pendulum","zero")["ok"].as<bool>());
  assert(ask(config,"pc",6,"pendulum","enable")["ok"].as<bool>());
  assert(pendulumEnabled);
  // Local sensor computation persists, but a network-issued ENABLE owns a lease.
  closesocket(config); runFor(10);
  assert(!pendulumEnabled);
  command("pend mode emg"); command("hand input rms"); command("hand mode glove");
  fakeEmgAmplitude=40; runFor(300); // Re-arm the newly selected RMS input by release.
  fakeEmgAmplitude=110; runFor(300); assert(grip.gripped);
  command("hand on"); assert(!glove.enabled);
  command("pose open 180,180,180,180,180,180");
  command("pose close 110,110,110,110,110,0"); command("pose save"); assert(glove.posesReady);
  command("open"); runFor(300);
  for(unsigned i=0;i<6;++i) fakePots[i]=(i==5?3000:1000);
  command("close"); runFor(300); command("save"); assert(glove.calibrated && !glove.enabled);
  GloveController rebooted; rebooted.begin(); assert(rebooted.calibrated && rebooted.posesReady && !rebooted.enabled);
  command("hand on"); runFor(200);
  assert(glove.enabled && glove.radio.pressureFresh() && glove.radio.actuatorReady());
  assert(glove.angles[0]==110 && glove.angles[5]==0);
  command("pressure start"); runFor(150); command("pressure zero");
  for(int i=0;i<5;++i) fakePressures[i]=uint16_t(500+20*i);
  runFor(100); command("pressure span"); command("pressure save"); assert(glove.pressureCalibrated);
  command("hand on"); runFor(150); command("hand on"); runFor(50);
  for(int i=0;i<5;++i) assert(glove.motorDuty[i]==255 && fakePwm[MOTOR_PINS[i]]==255);
  fakePressures[2]=750; runFor(60);
  assert(glove.motorDuty[2]>0 && glove.motorDuty[2]<255 && glove.motorDuty[1]==255);
  fakeRfFailure=true; unsigned reads=fakeEmgReads; uint32_t gaps=emgGaps; runFor(1000);
  assert(fakeEmgReads-reads>=490 && emgGaps==gaps && !glove.radio.pressureFresh());
  for(int i=0;i<5;++i) assert(glove.motorDuty[i]==0);
  assert(!glove.enabled); fakeRfFailure=false; runFor(400);
  assert(!glove.enabled); command("hand off"); // RF recovery never replays the closed pose.
  command("pend on"); assert(pendulumEnabled && !pendGrip.gripped);
  runFor(250); assert(!pendGrip.gripped);
  fakeEmgAmplitude=40; runFor(300); assert(pendGrip.armed);
  fakeEmgAmplitude=110; runFor(300); assert(pendGrip.gripped);
  stmReporting=false; runFor(1100); assert(pendulumLink.linked() && !pendulumEnabled);
  stmReporting=true; runFor(100); assert(pendulumLink.stmFresh(millis()) && !pendulumEnabled);
  command("pend off"); assert(!pendulumEnabled);
  // S3-only held motion uses unchanged single-turn frames and explicit STOP.
  fakeWorn=false; fakeEmgAmplitude=1000;
  tiltTest.clear(); // Earlier TCP zero case must not supply this scenario's reference.
  command("pend mode tilt_test"); command("stream tilt"); command("pend on"); assert(!pendulumEnabled);
  command("tilt zero"); assert(tiltTest.ready() && !pendulumEnabled);
  runFor(600); assert(tiltTest.armed);
  unsigned tiltPreview=gestureCount;
  fakeGyro[2]=2620; runFor(300); assert(tiltTest.moving && gestureCount==tiltPreview+1);
  fakeGyro[2]=0; runFor(600); assert(!tiltTest.moving);
  command("pend on"); runFor(600); assert(pendulumEnabled && !wearNow);
  NetworkRequest tiltEnable={}; tiltEnable.device=CommandDevice::PENDULUM;
  tiltEnable.action=CommandAction::ENABLE; tiltEnable.source=CommandSource::PC;
  const char *tiltError=nullptr;
  assert(handleNetwork(tiltEnable,tiltError) && pendulumEnabled);
  runFor(600); assert(tiltTest.armed);
  JsonDocument tiltStatus; buildNetworkStatus(tiltStatus.to<JsonObject>());
  assert(tiltStatus["pendulum"]["mode"].as<std::string>()=="tilt_test");
  size_t motionWireStart=uartFrames.size();
  unsigned linkCheckEvent=turnEvent; bool linkCheckEnabled=pendulumEnabled;
  command("link");
  assert(Serial.output.find("LINK,wifi:3,bridge:1,stm_fresh:1,stm_rx:")!=std::string::npos);
  assert(turnEvent==linkCheckEvent && pendulumEnabled==linkCheckEnabled);
  fakeGyro[2]=524; runFor(300); assert(tiltTest.moving && turnEvent==1 && tiltTurnInFlight); // Gentle 4 dps starts.
  reportedStmState=3; runFor(3000); assert(tiltTest.moving && pendulumEnabled && turnEvent==1 && tiltSawBusy);
  fakeAccel[2]=0; fakeGyro[2]=31440; runFor(300); // Strong shake near 0g / 240 dps stays active.
  assert(imuReady && tiltTest.moving && pendulumEnabled && turnEvent==1);
  fakeAccel[2]=16384; fakeGyro[2]=2620;
  reportedStmState=0; runFor(300); assert(turnEvent==2 && tiltTurnInFlight);
  reportedStmState=3; runFor(300); assert(tiltSawBusy);
  fakeWorn=true; fakeEmgAmplitude=40; runFor(300);
  fakeEmgAmplitude=1000; runFor(350); assert(grip.gripped && strength>500);
  for(size_t i=motionWireStart;i<uartFrames.size();++i) assert(!(uartFrames[i].flags&CONTROL_GRIP));
  // Static tilt stops the incomplete circle, retries invalid frames, then neutral ACK.
  size_t stopWireStart=uartFrames.size();
  fakeAccel[1]=8192; fakeAccel[2]=14189; fakeGyro[2]=0; runFor(1000);
  assert(!tiltTest.moving && pendulumEnabled && !tiltStopPending && !tiltTurnInFlight && reportedStmState==0);
  bool sawStop=false; for(size_t i=stopWireStart;i<uartFrames.size();++i) if(!uartFrames[i].flags) sawStop=true;
  assert(sawStop && uartFrames.back().flags==CONTROL_VALID && !uartFrames.back().direction);
  // A new movement can restart from that tilted pose, with no reference return.
  fakeGyro[2]=2620; runFor(300); assert(tiltTest.moving && turnEvent==3);
  reportedStmState=3; runFor(300);
  fakeMpuConnected=false; runFor(100); assert(!pendulumEnabled && !uartFrames.back().flags);
  fakeMpuConnected=true; fakeGyro[2]=0; command("c"); assert(imuReady && !pendulumEnabled);
  command("tilt zero"); runFor(600); command("pend on"); runFor(600);
  fakeGyro[2]=2620; runFor(300);  assert(tiltTest.moving);
  reportedStmState=3; runFor(300);
  stmReporting=false; runFor(1100); assert(!pendulumEnabled);
  stmReporting=true; runFor(400); assert(!pendulumEnabled);
  command("pend on"); runFor(600); assert(pendulumEnabled && !tiltTest.moving); // Held motion cannot resume.
  fakeGyro[2]=0; runFor(800); assert(tiltTest.armed);
  fakeGyro[2]=2620; runFor(300); assert(tiltTest.moving);
  // If STM never starts a request (e.g. its existing target limit), disable; no resend storm.
  runFor(1500); assert(!pendulumEnabled && Serial.output.find("MOTION_STM_TURN_NOT_STARTED")!=std::string::npos);
  command("estop"); assert(!pendulumEnabled && !tiltTest.moving);
  fakeGyro[2]=0; fakeAccel[1]=0; fakeAccel[2]=16384; command("c");
  command("pend mode emg"); fakeWorn=true; fakeEmgAmplitude=40; runFor(300);
  command("learn left"); command("hand on"); assert(!glove.enabled && swipeLearner.active);
  runFor(300); fakeAccel[1]=8192; runFor(50); fakeAccel[1]=0; runFor(300);
  assert(swipeReady && !swipeLearner.active && swipeAxis.left[1]>0.99f);
  unsigned previewBefore=gestureCount;
  fakeAccel[1]=8192; runFor(60); fakeAccel[1]=-8192; runFor(100); fakeAccel[1]=0; runFor(800);
  assert(gestureCount==previewBefore+1 && !pendulumEnabled);
  fakeEmgAmplitude=40; command("pend on"); runFor(300); unsigned eventBefore=turnEvent;
  fakeAccel[1]=8192; runFor(60); fakeAccel[1]=-8192; runFor(100); fakeAccel[1]=0; runFor(800);
  assert(turnEvent==eventBefore+1 && lastDirection==CONTROL_LEFT && !pendGrip.gripped);
  fakeAccel[1]=-8192; runFor(60); fakeAccel[1]=8192; runFor(100); fakeAccel[1]=0; runFor(800);
  assert(turnEvent==eventBefore+2 && lastDirection==CONTROL_RIGHT);
  unsigned rotationBefore=gestureCount;
  fakeGyro[2]=6550; runFor(600); fakeGyro[2]=0; runFor(800); assert(gestureCount==rotationBefore);
  fakeAccel[0]=8192; runFor(100); fakeAccel[0]=0; runFor(800); assert(gestureCount==rotationBefore);
  command("hand mode emg"); command("hand on"); runFor(300); assert(handGrip.armed && glove.enabled);
  fakeMpuConnected=false; runFor(100); assert(!imuReady && !pendulumEnabled && glove.enabled);
  fakeEmgAmplitude=110; runFor(300); assert(handGrip.gripped && glove.angles[5]==0);
  fakeWorn=false; runFor(20); assert(!glove.enabled); command("estop");
  // Temporary contact input: zero/detachment is OPEN, not a permanent disable.
  command("hand input contact");
  assert(handEmgInput==HandEmgInput::CONTACT && glove.mode==HandMode::EMG && !glove.enabled);
  assert(Serial.output.find("ACK,HAND_INPUT,contact,OFF")!=std::string::npos);
  runFor(300); assert(handContact.armed && !handContact.gripped && !glove.enabled);
  command("hand on"); runFor(100);
  if (!glove.enabled) command("hand on");
  runFor(300); assert(glove.enabled && glove.angles[5]==180 && !imuReady);
  fakeEmgAmplitude=1000; fakeWorn=true; runFor(350);
  assert(handContact.gripped && selectedHandGrip() && glove.angles[5]==0);
  command("hand input typo"); assert(glove.enabled && handEmgInput==HandEmgInput::CONTACT);
  fakeEmgAmplitude=300; runFor(350); assert(handContact.gripped && glove.angles[5]==0);
  fakeEmgAmplitude=40; runFor(350);
  assert(glove.enabled && !handContact.gripped && glove.angles[5]==180);
  fakeEmgAmplitude=1000; runFor(350); assert(handContact.gripped && glove.angles[5]==0);
  fakeWorn=false; runFor(350);
  assert(glove.enabled && !selectedHandGrip() && glove.angles[5]==180);
  fakeWorn=true; runFor(350); assert(glove.enabled && glove.angles[5]==0);
  fakeRfFailure=true; runFor(400); assert(!glove.enabled);
  fakeRfFailure=false; runFor(400); assert(!glove.enabled && glove.angles[5]==180);
  command("hand on"); runFor(100);
  if (!glove.enabled) command("hand on");
  runFor(300); assert(glove.enabled && !handContact.armed && glove.angles[5]==180);
  fakeEmgAmplitude=40; runFor(350); assert(handContact.armed && !selectedHandGrip());
  fakeEmgAmplitude=1000; runFor(350); assert(handContact.gripped && selectedHandGrip());
  fakeWorn=false; runFor(350); fakeWorn=true; runFor(350);
  assert(glove.enabled && handContact.gripped && glove.angles[5]==0);
  command("estop"); runFor(300); assert(!glove.enabled && !handContact.gripped);
  for(int i=0;i<5;++i) assert(glove.motorDuty[i]==0);
  command("hand input rms"); fakeWorn=false; runFor(350); command("hand on");
  assert(handEmgInput==HandEmgInput::RMS && !glove.enabled);
  assert(Serial.output.find("ERROR,WEAR_REQUIRED")!=std::string::npos);
  // TCP ENABLE respects the selected local input, without requiring contact
  // during neutral arming. Selecting NETWORK ignores the contact preview.
  SOCKET contactPc=connectPc();
  assert(ask(contactPc,"pc",1,"all","hello")["ok"].as<bool>());
  command("hand input contact");
  bool contactEnabled=ask(contactPc,"pc",2,"hand","enable")["ok"].as<bool>();
  if (!contactEnabled) {
    runFor(100); assert(ask(contactPc,"pc",3,"hand","enable")["ok"].as<bool>());
  }
  runFor(250); assert(glove.enabled && !wearNow && glove.angles[5]==180);
  assert(ask(contactPc,"pc",4,"all","status")["status"]["hand"]["emg_input"].as<std::string>()=="contact");
  fakeWorn=true; runFor(350); assert(handContact.gripped && selectedHandGrip());
  closesocket(contactPc);runFor(20);assert(!glove.enabled);
  contactPc=connectPc();assert(ask(contactPc,"pc",1,"all","hello")["ok"].as<bool>());
  assert(!glove.enabled); // New connection cannot restore a local input's old enable.
  assert(ask(contactPc,"pc",5,"hand","mode",",\"mode\":\"network\"")["ok"].as<bool>());
  bool networkEnabled=ask(contactPc,"pc",6,"hand","enable")["ok"].as<bool>();
  if (!networkEnabled) {
    runFor(100); assert(ask(contactPc,"pc",7,"hand","enable")["ok"].as<bool>());
  }
  fakeWorn=false; runFor(300);
  assert(ask(contactPc,"pc",8,"all","heartbeat")["ok"].as<bool>());
  fakeWorn=true; runFor(350);
  assert(handContact.gripped && glove.enabled && !selectedHandGrip() && glove.angles[5]==180);
  command("hand input rms"); fakeWorn=false; runFor(100);
  closesocket(contactPc); runFor(20);
  // Both sensors absent: NETWORK must still operate through the actual TCP service.
  SOCKET pc=connectPc(),eye=connectPc();
  assert(ask(pc,"pc",1,"all","hello")["ok"].as<bool>());
  assert(ask(eye,"eye",1,"all","hello")["ok"].as<bool>());
  assert(ask(pc,"pc",2,"pendulum","mode",",\"mode\":\"network\"")["ok"].as<bool>());
  assert(ask(pc,"pc",3,"pendulum","enable")["ok"].as<bool>());
  runFor(5); assert(pendulumLink.neutralReady());
  assert(ask(pc,"pc",4,"pendulum","start")["ok"].as<bool>()); runFor(60);
  assert(networkBalance && pendulumEnabled && !imuReady && !wearNow);
  assert(uartFrames.back().flags==(CONTROL_VALID|CONTROL_GRIP));
  assert(ask(pc,"pc",5,"pendulum","stop")["ok"].as<bool>());
  assert(ask(pc,"pc",6,"pendulum","left")["ok"].as<bool>()); runFor(60);
  assert(!networkBalance && uartFrames.back().flags==CONTROL_VALID);
  assert(ask(eye,"eye",2,"hand","mode",",\"mode\":\"network\"")["ok"].as<bool>());
  assert(!ask(eye,"eye",3,"hand","enable")["ok"].as<bool>());
  runFor(100); assert(ask(eye,"eye",4,"hand","enable")["ok"].as<bool>());
  assert(ask(eye,"eye",5,"hand","close")["ok"].as<bool>()); assert(glove.angles[5]==0);
  assert(!ask(pc,"pc",7,"hand","close")["ok"].as<bool>());
  assert(ask(eye,"eye",6,"hand","mode",",\"mode\":\"network\"")["ok"].as<bool>());
  assert(!glove.enabled && glove.angles[5]==180); // Even same-mode re-selection stops.
  command("CMD_V1,POSE,10,20,30,40,50,60");
  assert(ask(eye,"eye",7,"hand","enable")["ok"].as<bool>()); assert(glove.angles[5]==180);
  assert(ask(eye,"eye",8,"hand","close")["ok"].as<bool>());
  command("CMD_V1,POSE,10,20,30,40,50,60"); assert(glove.angles[5]==0);
  closesocket(pc); runFor(20); assert(!pendulumEnabled && glove.enabled);
  unsigned events=turnEvent; SOCKET pc2=connectPc();
  assert(ask(pc2,"pc",1,"all","hello")["ok"].as<bool>());
  assert(!ask(pc2,"pc",2,"pendulum","start")["ok"].as<bool>() && turnEvent==events);
  closesocket(pc2); runFor(20);
  runFor(510); assert(!glove.enabled);
  for(int i=0;i<5;++i) assert(glove.motorDuty[i]==0);
  closesocket(eye); runFor(20);
  // Bridge restart cannot restore a stored movement request.
  fakeWorn=true; imuReady=true; lastGoodImu=micros(); command("pend on");
  bridgeAlive=false; runFor(300); assert(!pendulumEnabled && !pendulumLink.linked());
  bridgeAlive=true; gateway.begin(millis()); runFor(800); assert(pendulumLink.linked() && !pendulumEnabled);
  Serial.feed("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"); runFor(40);
  assert(Serial.output.find("ERROR,LINE_TOO_LONG")!=std::string::npos);
  JsonDocument status; buildNetworkStatus(status.to<JsonObject>()); assert(measureJson(status)<900);
  // RF transmitter restart learns the Nano counter from safe-open ACK only.
  GloveRadio replacement; assert(replacement.begin());
  int16_t safe[6]={180,180,180,180,180,180}; fakeFeedbackSequence=20000;
  replacement.tick(true,safe); fakeUs+=2000; replacement.tick(true,safe);
  assert(replacement.sequence==20000 && !replacement.pressureFresh());
  fakeFeedbackSequence=-1; fakeUs+=21000; replacement.tick(true,safe); fakeUs+=2000; replacement.tick(true,safe);
  assert(replacement.sequence==20001 && replacement.pressureFresh());
  WiFi.state=0; networkControl.tick(millis());
  puts("Actual S3 runtime: ADC pins, EMG/contact independence, press/release, swipe/tilt gestures, tilt-only wire requests, source isolation, neutral/rearm, pressure/PWM and reconnect PASS");
}
