#include <cassert>
#include "../hand_nano/hand_controller/hand_controller.ino"
static void sendControl(uint16_t seq,int angle) {
  std::vector<uint8_t> packet(14);packet[0]=uint8_t(seq);packet[1]=uint8_t(seq>>8);
  for(int i=0;i<6;++i) {packet[2+2*i]=uint8_t(angle);packet[3+2*i]=uint8_t(angle>>8);}
  radio.packets.push_back(packet); loop();
}
int main() {
 setup(); assert(pressureSampled && filteredPressure[0]==1000 && !(alarmFlags&31));
 if(!SAFE_POSE_VERIFIED) {
   assert(!actuatorReady && !attachedServos);sendControl(1,60);
   assert(controlReceived && servos[0].value==-1 && !(alarmFlags&0x20));
   puts("Production unverified Nano: RF/ADC available, no servo attach PASS");return 0;
 }
 assert(attachedServos==6 && actuatorReady);
 sendControl(1000,60); assert(controlReceived && servos[0].value==60);
 nanoTime=1001; loop(); assert(!controlReceived && servos[0].value==SAFE_SERVO_ANGLES[0]);
 sendControl(1000,60); assert(!controlReceived && servos[0].value==SAFE_SERVO_ANGLES[0]);
 sendControl(999,60); assert(!controlReceived);
 sendControl(1001,70); assert(controlReceived && servos[0].value==70);
 sendControl(1002,181); assert(controlPacket.sequence==1001 && servos[0].value==70);
 nanoPressures[0]=0; nanoPressures[1]=800;sendControl(1002,75);
 assert(filteredPressure[0]==750 && filteredPressure[1]==950 && filteredPressure[2]==1000);
 assert(radio.feedback.size()==13 && radio.feedback[12]==0x20);
 // A genuine wrap is new; replay after the local timeout never restores closure.
 controlPacket.sequence=65535; sendControl(0,80);assert(servos[5].value==80);
 nanoTime+=1001;loop();sendControl(0,80);assert(!controlReceived && servos[5].value==SAFE_SERVO_ANGLES[5]);
 puts("Actual Nano runtime: startup, five ADC, all-angle rejection, timeout, old packet and wrap PASS");
}
