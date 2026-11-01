#pragma once
#include <stdint.h>
#include <string.h>
// Input arbitration has no radio, storage or clock dependencies.
class LocalHandControl {
 public:
  enum Owner : uint8_t { GLOVE, CONTACT_OPEN, CONTACT_CLOSED };
  void reset(const int16_t *pose,uint32_t frame) {
    memcpy(anchor,pose,sizeof(anchor)); lastFrame=frame;
    owner=CONTACT_OPEN; armed=lastPressed=false;
  }
  Owner update(bool pressed,const int16_t *pose,uint32_t frame) {
    bool press=armed && pressed && !lastPressed;
    bool release=armed && !pressed && lastPressed;
    if (!pressed) armed=true;
    lastPressed=pressed;
    if (press || release) {
      owner=press?CONTACT_CLOSED:CONTACT_OPEN;
      memcpy(anchor,pose,sizeof(anchor));lastFrame=frame;
      return owner;
    }
    if (pressed) return owner; // Electrode wins even over a simultaneous glove frame.
    if (frame!=lastFrame) {
      lastFrame=frame;
      bool moved=false;
      for (unsigned i=0;i<6;++i) {
        int delta=int(pose[i])-anchor[i];if(delta>=6 || delta<=-6)moved=true;
      }
      if(moved)owner=GLOVE;
    }
    return owner;
  }
  const char *name() const {return owner==GLOVE?"glove":owner==CONTACT_CLOSED?"contact_closed":"contact_open";}
 private:
  Owner owner=CONTACT_OPEN;
  bool armed=false,lastPressed=false;
  int16_t anchor[6]={};uint32_t lastFrame=0;
};
