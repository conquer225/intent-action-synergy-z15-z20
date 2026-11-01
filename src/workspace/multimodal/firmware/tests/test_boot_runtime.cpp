#include "boot_test_support.h"
static void localControl(bool usbBlocked=false) {
  saveConfirmedPoses(); gateway.begin(0);
  if (usbBlocked) Serial.txFree=0;
  unsigned stalledBefore=Serial.stalledWrites;
  fakeEmgAmplitude=2000; setup(); runFor(3500);
  auto d=status();
  assert(d["hand"]["enabled"].as<bool>());
  assert(d["hand"]["mode"].as<std::string>()=="emg");
  assert(d["hand"]["emg_input"].as<std::string>()=="contact");
  assert(d["pendulum"]["enabled"].as<bool>());
  assert(d["pendulum"]["mode"].as<std::string>()=="tilt_test");
  for (unsigned i=0;i<5;++i) assert(d["hand"]["vibration_pwm"][i].as<unsigned>()==0);
  for (auto f:uartFrames) { assert(!(f.flags&CONTROL_GRIP)); assert(!f.direction); }
  assertOpen(); // Press held through boot must first be released.
  fakeEmgAmplitude=40; runFor(350); assertOpen();
  fakeEmgAmplitude=2000; runFor(350); assertClosed();
  fakeEmgAmplitude=40; runFor(350); assertOpen();
  size_t motionStart=uartFrames.size(); fakeGyro[2]=524; runFor(300);
  unsigned left=0;
  for (size_t i=motionStart;i<uartFrames.size();++i)
    if (uartFrames[i].flags==CONTROL_VALID && uartFrames[i].direction==CONTROL_LEFT) ++left;
  assert(left==1); // The existing bridge forwards a turn event only once.
  fakeGyro[2]=0; runFor(800);
  assert(uartFrames.back().flags==CONTROL_VALID && !uartFrames.back().direction);
  assert(Serial.stalledWrites==stalledBefore);
  puts("Boot local control: contact release-before-press and MPU motion/stop without USB commands PASS");
}
static void stoppedWhileWaiting() {
  saveConfirmedPoses(); gateway.begin(0); fakeRfFailure=true; bridgeAlive=false;
  setup(); runFor(600); command("estop");
  fakeRfFailure=false; bridgeAlive=true; gateway.begin(millis()); runFor(3500);
  auto d=status(); assert(!d["hand"]["enabled"].as<bool>() && !d["pendulum"]["enabled"].as<bool>());
  assertOpen();
  puts("Boot cancellation: estop before hardware arrives remains stopped PASS");
}
static void movingAtBoot() {
  saveConfirmedPoses(); gateway.begin(0); fakeGyro[2]=2620;
  setup(); runFor(1500);
  auto d=status(); assert(d["hand"]["enabled"].as<bool>());
  assert(!d["pendulum"]["enabled"].as<bool>() && !d["sensors"]["imu"].as<bool>());
  uint32_t gaps=d["sensors"]["emg_gaps"].as<uint32_t>(); unsigned reads=fakeEmgReads;
  fakeGyro[2]=0; runFor(3500); d=status();
  assert(d["pendulum"]["enabled"].as<bool>() && d["sensors"]["imu"].as<bool>());
  assert(d["hand"]["enabled"].as<bool>() && d["sensors"]["emg_gaps"].as<uint32_t>()==gaps);
  assert(fakeEmgReads-reads>=1700);
  fakeEmgAmplitude=2000; runFor(350); assertClosed();
  puts("Boot MPU: moving at startup waits, then quiet calibration completes without interrupting hand PASS");
}
static void lateHardware() {
  saveConfirmedPoses(); gateway.begin(0);
  fakeRfPresent=false; fakeMpuConnected=false; bridgeAlive=false;
  setup(); runFor(1500);
  auto d=status(); assert(!d["hand"]["enabled"].as<bool>() && !d["pendulum"]["enabled"].as<bool>());
  fakeRfPresent=true; runFor(2000); d=status();
  assert(d["hand"]["enabled"].as<bool>() && !d["pendulum"]["enabled"].as<bool>());
  fakeMpuConnected=true; bridgeAlive=true; gateway.begin(millis()); runFor(4000); d=status();
  assert(d["hand"]["enabled"].as<bool>() && d["pendulum"]["enabled"].as<bool>());
  fakeRfFailure=true; bridgeAlive=false; runFor(1000); d=status();
  assert(!d["hand"]["enabled"].as<bool>() && !d["pendulum"]["enabled"].as<bool>());
  fakeRfFailure=false; bridgeAlive=true; gateway.begin(millis()); runFor(3500); d=status();
  assert(!d["hand"]["enabled"].as<bool>() && !d["pendulum"]["enabled"].as<bool>());
  assertOpen();
  puts("Boot devices: independent late power, one-time activation, runtime loss stays stopped PASS");
}
static void remoteInterfaces() {
  saveConfirmedPoses(); gateway.begin(0); fakeRfFailure=true; bridgeAlive=false;
  setup(); runFor(600);
  SOCKET eye=connectSource(), brain=connectSource(); unsigned es=1, bs=1;
  assert(ask(eye,"eye",es++,"all","hello")["ok"].as<bool>());
  assert(ask(brain,"brain",bs++,"all","hello")["ok"].as<bool>());
  assert(ask(eye,"eye",es++,"hand","mode",",\"mode\":\"network\"")["ok"].as<bool>());
  assert(ask(brain,"brain",bs++,"pendulum","mode",",\"mode\":\"network\"")["ok"].as<bool>());
  fakeRfFailure=false; bridgeAlive=true; gateway.begin(millis());
  for (unsigned n=0;n<20;++n) {
    runFor(100);
    assert(ask(eye,"eye",es++,"all","heartbeat")["ok"].as<bool>());
    assert(ask(brain,"brain",bs++,"all","heartbeat")["ok"].as<bool>());
  }
  auto d=status(); assert(!d["hand"]["enabled"].as<bool>() && !d["pendulum"]["enabled"].as<bool>());
  bool enabled=ask(eye,"eye",es++,"hand","enable")["ok"].as<bool>();
  if (!enabled) { runFor(100); assert(ask(eye,"eye",es++,"hand","enable")["ok"].as<bool>()); }
  assert(ask(eye,"eye",es++,"hand","close")["ok"].as<bool>()); assertClosed();
  fakeEmgAmplitude=2000; runFor(300); assertClosed();
  assert(ask(eye,"eye",es++,"hand","open")["ok"].as<bool>()); assertOpen();
  assert(!ask(brain,"brain",bs++,"hand","mode",",\"mode\":\"network\"")["ok"].as<bool>());
  assert(ask(eye,"eye",es++,"hand","disable")["ok"].as<bool>());
  assert(ask(brain,"brain",bs++,"hand","mode",",\"mode\":\"network\"")["ok"].as<bool>());
  enabled=ask(brain,"brain",bs++,"hand","enable")["ok"].as<bool>();
  if (!enabled) { runFor(100); assert(ask(brain,"brain",bs++,"hand","enable")["ok"].as<bool>()); }
  assert(ask(brain,"brain",bs++,"hand","close")["ok"].as<bool>()); assertClosed();
  assert(ask(brain,"brain",bs++,"pendulum","enable")["ok"].as<bool>()); runFor(100);
  assert(ask(brain,"brain",bs++,"pendulum","left")["ok"].as<bool>());
  runFor(600); d=status();
  assert(!d["hand"]["enabled"].as<bool>() && !d["pendulum"]["enabled"].as<bool>());
  runFor(2000); d=status();
  assert(!d["hand"]["enabled"].as<bool>() && !d["pendulum"]["enabled"].as<bool>());
  assertOpen(); closesocket(eye); closesocket(brain);
  puts("Boot remote interfaces: eye/brain takeover, ownership, OPEN/CLOSE, pendulum and heartbeat expiry PASS");
}
static void independentStop(bool hand) {
  saveConfirmedPoses(); gateway.begin(0); fakeRfFailure=true; bridgeAlive=false;
  setup(); runFor(600); command(hand?"hand off":"pend off");
  fakeRfFailure=false; bridgeAlive=true; gateway.begin(millis()); runFor(4000);
  auto d=status();
  assert(d["hand"]["enabled"].as<bool>()==!hand);
  assert(d["pendulum"]["enabled"].as<bool>()==hand);
  puts("Boot independent cancellation: stopping one device preserves the other startup PASS");
}
static void unavailableHand(const char *kind) {
  if (!strcmp(kind,"unverified")) { saveConfirmedPoses(); fakeRfFlags=0; }
  gateway.begin(0); setup(); runFor(4000);
  auto d=status(); assert(!d["hand"]["enabled"].as<bool>() && d["pendulum"]["enabled"].as<bool>());
  assertOpen();
  puts("Boot hand gate: missing poses or unverified Nano never enables servos PASS");
}
static void directGlove() {
  saveConfirmedPoses(); gateway.begin(0); setup(); runFor(3500);
  assert(pendulumEnabled && !glove.calibrated);
  const uint16_t opened[6]={4095,4095,4095,4095,0,4095};
  memcpy(fakePots,opened,sizeof(opened)); runFor(300);
  command("pot direct"); command("hand on"); runFor(150);
  if (!glove.enabled) command("hand on");
  runFor(200);
  assert(glove.mode==HandMode::GLOVE && glove.enabled && pendulumEnabled);
  assertOpen();
  const uint16_t closed[6]={3593,3319,3208,3111,3002,3603};
  memcpy(fakePots,closed,sizeof(closed)); runFor(400);
  auto d=status();
  for (unsigned i=0;i<5;++i) assert(d["hand"]["angles"][i].as<int>()==110);
  assert(d["hand"]["angles"][5].as<int>()==0);
  for (unsigned i=0;i<5;++i) assert(fakeSentAngles[i]==110);
  assert(fakeSentAngles[5]==0);
  assert(d["hand"]["glove_mapping"].as<std::string>()=="direct");
  assert(!d["hand"]["pot_calibrated"].as<bool>());
  const uint16_t middle[6]={3844,3707,3651,3603,1501,3849};
  memcpy(fakePots,middle,sizeof(middle)); runFor(400); d=status();
  for (unsigned i=0;i<5;++i) assert(d["hand"]["angles"][i].as<int>()>=144 && d["hand"]["angles"][i].as<int>()<=145);
  assert(d["hand"]["angles"][5].as<int>()>=90 && d["hand"]["angles"][5].as<int>()<=91);
  memcpy(fakePots,opened,sizeof(opened)); fakePots[4]=3002; runFor(400); d=status();
  for (unsigned i=0;i<5;++i) assert(d["hand"]["angles"][i].as<int>()==180);
  assert(d["hand"]["angles"][5].as<int>()==0);
  memcpy(fakePots,opened,sizeof(opened)); fakePots[5]=3603; runFor(400); d=status();
  for (unsigned i=0;i<4;++i) assert(d["hand"]["angles"][i].as<int>()==180);
  assert(d["hand"]["angles"][4].as<int>()==110 && d["hand"]["angles"][5].as<int>()==180);
  fakeRfFailure=true; runFor(500); assert(!glove.enabled && pendulumEnabled);
  fakeRfFailure=false; runFor(500); assert(!glove.enabled);
  puts("Direct glove: six independent routes, GPIO10 pinky and GPIO9 thumb side, MPU retained and RF loss stops PASS");
}
static void nanoGlove() {
  saveConfirmedPoses(); gateway.begin(0); fakeRfFailure=true; bridgeAlive=false;
  setup(); runFor(600); command("pot nano");
  fakeRfFailure=false; bridgeAlive=true; gateway.begin(millis()); runFor(3500);
  assert(!glove.enabled && pendulumEnabled); // Early selection cancels pending boot enable.
  const uint16_t opened[6]={4095,4095,4095,4095,0,4095};
  memcpy(fakePots,opened,sizeof(opened)); runFor(300);
  command("pot nano"); runFor(700);
  assert(!glove.enabled && pendulumEnabled);
  assert(status()["hand"]["glove_mapping"].as<std::string>()=="nano");
  command("hand on"); runFor(150); if (!glove.enabled) command("hand on");
  assert(glove.enabled && !glove.calibrated); runFor(300); assertOpen();
  // Known old-Nano examples: ADC900 -> 130 thumb/125 fingers; ADC801 -> 90/81.
  const uint16_t legacy900[6]={3603,3603,3603,3603,0,3603};
  memcpy(fakePots,legacy900,sizeof(legacy900)); runFor(400);
  auto d=status(); assert(d["hand"]["angles"][0].as<int>()==130);
  for (unsigned i=1;i<5;++i) assert(d["hand"]["angles"][i].as<int>()==125);
  const uint16_t legacy801[6]={3204,3204,3204,3204,0,3204};
  memcpy(fakePots,legacy801,sizeof(legacy801)); runFor(400); d=status();
  assert(d["hand"]["angles"][0].as<int>()>=90 && d["hand"]["angles"][0].as<int>()<=91);
  for (unsigned i=1;i<5;++i) assert(d["hand"]["angles"][i].as<int>()>=81 && d["hand"]["angles"][i].as<int>()<=82);
  for (unsigned i=0;i<6;++i) assert(fakeSentAngles[i]==d["hand"]["angles"][i].as<int>());
  memcpy(fakePots,opened,sizeof(opened)); fakePots[5]=3204; runFor(400); d=status();
  for (unsigned i=0;i<4;++i) assert(d["hand"]["angles"][i].as<int>()==180);
  assert(d["hand"]["angles"][4].as<int>()<=82 && d["hand"]["angles"][5].as<int>()==180);
  memcpy(fakePots,opened,sizeof(opened)); fakePots[4]=1504; runFor(400); d=status();
  for (unsigned i=0;i<5;++i) assert(d["hand"]["angles"][i].as<int>()==180);
  assert(d["hand"]["angles"][5].as<int>()==90);
  for (auto &p:fakePots) p=0; runFor(400); d=status();
  for (unsigned i=0;i<5;++i) assert(d["hand"]["angles"][i].as<int>()==0);
  assert(d["hand"]["angles"][5].as<int>()==180);
  fakePots[4]=4095; runFor(400); assert(status()["hand"]["angles"][5].as<int>()==0);
  command("pot direct"); assert(!glove.enabled && pendulumEnabled);
  command("pot nano"); command("hand on"); runFor(150);
  if (!glove.enabled) command("hand on");
  runFor(300); assert(glove.enabled);
  fakeRfFailure=true; runFor(500); assert(!glove.enabled && pendulumEnabled);
  fakeRfFailure=false; runFor(500); assert(!glove.enabled);
  command("pot direct"); assert(status()["hand"]["glove_mapping"].as<std::string>()=="direct");
  assert(!glove.enabled && pendulumEnabled);
  puts("Nano glove: original integer curves, six routes, 0..180 clamps, explicit activation and RF watchdog PASS");
}
static void locateGlove() {
  saveConfirmedPoses(); gateway.begin(0); setup(); runFor(3500);
  assert(glove.enabled && pendulumEnabled && fakePwmAttached[8]);
  command("pot locate");
  unsigned writes8=fakePinWrites[8];
  assert(Serial.output.find("ACK,POT_LOCATE,HAND_OFF,GPIO3_GPIO8,RESTART_TO_EXIT")!=std::string::npos);
  assert(!glove.enabled && pendulumEnabled);
  assert(!fakePwmAttached[8] && fakePinModes[8]==INPUT);
  command("stream pots"); runFor(200);
  assert(Serial.output.find("probe3:1234\tprobe8:2345")!=std::string::npos);
  fakeProbe3=300; fakeProbe8=3500; runFor(200);
  assert(Serial.output.find("probe3:300\tprobe8:3500")!=std::string::npos);
  command("hand on"); command("pot direct"); command("hand on"); runFor(1000);
  assert(!glove.enabled && pendulumEnabled && fakePinWrites[8]==writes8);
  for (unsigned i=0;i<6;++i) assert(fakeSentAngles[i]==180);
  puts("Glove locate: released ADC input, live probes, blocked output and independent pendulum PASS");
}
int main(int argc,char **argv) {
  if (argc>1 && !strcmp(argv[1],"glove-nano")) { nanoGlove(); return 0; }
  if (argc>1 && !strcmp(argv[1],"glove-locate")) { locateGlove(); return 0; }
  if (argc>1 && !strcmp(argv[1],"glove-direct")) { directGlove(); return 0; }
  if (argc>1 && !strcmp(argv[1],"cancel")) stoppedWhileWaiting();
  else if (argc>1 && !strcmp(argv[1],"moving")) movingAtBoot();
  else if (argc>1 && !strcmp(argv[1],"late")) lateHardware();
  else if (argc>1 && !strcmp(argv[1],"remote")) remoteInterfaces();
  else if (argc>1 && !strcmp(argv[1],"hand-off")) independentStop(true);
  else if (argc>1 && !strcmp(argv[1],"pend-off")) independentStop(false);
  else if (argc>1 && (!strcmp(argv[1],"missing-poses") || !strcmp(argv[1],"unverified"))) unavailableHand(argv[1]);
  else if (argc>1 && !strcmp(argv[1],"usb-blocked")) localControl(true);
  else localControl();
}
