#include <winsock2.h>
#include <cassert>
#include <cstdio>
#define MULTICONTROL_AUTO_START 0 // Exercise the retained manual commissioning workflow.
#include "../esp32/MultiControlS3/MultiControlS3.ino"

static void runFor(unsigned ms) {
  uint64_t until=fakeUs+1000ULL*ms;
  while (fakeUs<until) { fakeUs+=200; loop(); }
}
static void command(const char *text) {
  Serial.feed(text); Serial.feed("\n"); runFor(20);
}
int main() {
  // Match the photographed near-vertical mounting and its -4 dps gyro bias.
  fakeAccel[0]=-15974; fakeAccel[1]=-360; fakeAccel[2]=1851;
  fakeGyro[0]=-524; fakeGyro[1]=-24; fakeGyro[2]=-52;
  fakeWorn=false;
  // Real Wi-Fi initialization can outlast the 100ms runtime sampling guard.
  fakeWifiStartupDelayMs=350;
  setup(); runFor(500);
  JsonDocument startup; buildNetworkStatus(startup.to<JsonObject>());
  assert(startup["sensors"]["imu"].as<bool>());
  assert(!startup["pendulum"]["enabled"].as<bool>() && !startup["hand"]["enabled"].as<bool>());
  assert(!wearNow);
  assert(!swipeReady); // Must teach LEFT in the new wearing orientation.
  command("learn left"); runFor(350);
  fakeAccel[1]+=2621; runFor(60); fakeAccel[1]-=2621;
  assert(swipeReady && !swipeLearner.active && swipeAxis.left[1]>0.99f);
  runFor(800);
  unsigned count=gestureCount;
  fakeAccel[1]+=2621; runFor(60); fakeAccel[1]-=2621;
  fakeAccel[1]-=5000; runFor(80); fakeAccel[1]+=5000;
  runFor(800);
  assert(gestureCount==count+1 && lastGesture==1 && imuReady);
  fakeAccel[1]-=2621; runFor(60); fakeAccel[1]+=2621;
  runFor(800);
  assert(gestureCount==count+2 && lastGesture==-1 && imuReady);
  assert(!pendulumEnabled && !glove.enabled); // Preview cannot enable actuators.
  command("pend on"); assert(!pendulumEnabled); // Wear safety still applies to real balance.
  // Small noise below threshold and forward/backward movements do not fire.
  fakeAccel[1]+=655; runFor(100); fakeAccel[1]-=655; runFor(800);
  fakeAccel[2]+=4000; runFor(100); fakeAccel[2]-=4000; runFor(800);
  assert(gestureCount==count+2 && imuReady);
  command("stream motion");
  runFor(100);
  assert(Serial.output.find("gesture_count:")!=std::string::npos);
  assert(Serial.output.find("ax_g:")!=std::string::npos);
  assert(Serial.output.find("motion_g:")!=std::string::npos);
  assert(Serial.output.find("rotation_dps:")!=std::string::npos);
  assert(fabsf(diagnosticAccel[0]-fakeAccel[0]/16384.0f)<0.0001f);
  command("c"); runFor(100);
  assert(imuReady && !swipeReady && !pendulumEnabled && !glove.enabled);
  // The runtime >100ms guard remains active after setup's timing reset.
  fakeUs+=150000; runFor(20);
  JsonDocument stalled; buildNetworkStatus(stalled.to<JsonObject>());
  assert(!stalled["sensors"]["imu"].as<bool>());
  command("c"); runFor(100);
  assert(imuReady);
  fakeMpuConnected=false; runFor(50);
  assert(!imuReady);
  // A rejected sensor record must report real values, rather than only a generic error.
  fakeMpuConnected=true;
  fakeAccel[0]=fakeAccel[1]=fakeAccel[2]=0;
  fakeGyro[0]=fakeGyro[1]=fakeGyro[2]=0;
  Serial.output.clear(); command("c");
  assert(Serial.output.find("MPU_CAL_REJECT,sample:1,reason:accel,accel:0.0000/0.0000/0.0000")!=std::string::npos);
  JsonDocument rejected; buildNetworkStatus(rejected.to<JsonObject>());
  assert(!rejected["sensors"]["imu"].as<bool>());
  assert(!rejected["pendulum"]["enabled"].as<bool>() && !rejected["hand"]["enabled"].as<bool>());
  puts("Production MPU runtime: vertical calibration, light left/right preview without EMG, braking/noise rejection, relearning and disconnect PASS");
}
