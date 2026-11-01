#include <cassert>
#include <cstdio>
#include "../firmware/MultiControlS3/GloveRadio.cpp"
static void exchange(GloveRadio& r){int16_t safe[6]={180,180,180,180,180,180};fakeUs+=21000;r.tick(true,safe);fakeUs+=2000;r.tick(true,safe);}
int main(){
 GloveRadio sender;assert(sender.begin());sender.sequence=10000;receiverSequence=0;receiverSeen=false;memset(feedbackBytes,0,13);
 exchange(sender);assert(sender.sequence==10001);assert(!sender.pressureFresh());
 exchange(sender);assert(sender.sequence==10002);assert(sender.pressureFresh());assert(sender.actuatorReady());
 GloveRadio restarted;assert(restarted.begin());receiverSequence=20000;receiverSeen=true;feedbackBytes[0]=0x20;feedbackBytes[1]=0x4e;feedbackBytes[12]=0x20;
 exchange(restarted);assert(restarted.sequence==20000);assert(!restarted.pressureFresh());
 exchange(restarted);assert(restarted.sequence==20001);assert(!restarted.pressureFresh());
 exchange(restarted);assert(restarted.pressureFresh());
 puts("RF_RESYNC_PASS receiver restart and sender restart, delayed ACK never rewinds accepted sender counter");
}
