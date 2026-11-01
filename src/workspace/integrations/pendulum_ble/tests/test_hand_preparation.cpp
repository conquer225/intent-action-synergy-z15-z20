#include <cassert>
#include <cstdio>
#include "../firmware/MultiControlS3/GloveRadio.cpp"
#include "../firmware/MultiControlS3/GloveController.cpp"

// Hardware adapters are inert; controller state and RF framing are production code.
bool HapticFeedback::begin(){return true;}
void HapticFeedback::stop(){}
void HapticFeedback::releasePinForInput(int){}
void HapticFeedback::tick(bool,bool,const HandFeedback&){}
bool HapticFeedback::command(char*,bool,const HandFeedback&){return false;}

static void advance(GloveController& hand,unsigned ms){
 for(unsigned n=0;n<ms;++n){fakeUs+=1000;hand.tick();}
}
int main(){
 GloveController hand;hand.begin();
 int16_t opened[6]={180,180,180,180,180,180};
 int16_t closed[6]={110,110,110,110,110,0};
 assert(hand.capturePose(false,opened));assert(hand.capturePose(true,closed));
 assert(hand.savePoses());
 hand.setMode(HandMode::NETWORK);
 // A typical wireless status reply arrives after the old 100 ms stop probe.
 advance(hand,220);
 assert(!hand.enabled);
 assert(hand.radio.actuatorReady());
 // A target while OFF cannot replace the preparation's verified OPEN frames.
 assert(hand.setNetworkPose(closed));advance(hand,40);
 for(int i=0;i<6;++i)assert(readLE16(lastControlBytes+2+2*i)==180);
 // Preparing never enables automatically and expires after one second.
 advance(hand,900);assert(!hand.enabled);
 const auto sent=transmittedCount;advance(hand,350);
 assert(transmittedCount==sent);assert(!hand.radio.pressureFresh());
 // Explicit retry of the same mode prepares again; stop cancels it.
 hand.setMode(HandMode::NETWORK);advance(hand,180);
 assert(hand.radio.actuatorReady());hand.stop();advance(hand,180);
 const auto stopped=transmittedCount;advance(hand,300);
 assert(transmittedCount==stopped);assert(!hand.enabled);
 // A new preparation still requires a distinct explicit enable.
 hand.setMode(HandMode::NETWORK);advance(hand,200);assert(hand.enable());
 assert(hand.enabled);hand.stop();assert(!hand.enabled);
 puts("HAND_PREPARATION_PASS bounded OPEN-only readiness, explicit enable and stop");
}
