#ifndef MULTI_GLOVE_RADIO_H
#define MULTI_GLOVE_RADIO_H
#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>
#include "GloveLogic.h"

class GloveRadio {
 public:
  bool begin();
  void tick(bool enabled, const int16_t *angles);
  void cancel();
  void invalidateFeedback() { feedbackSeen=false; }
  bool ready = false, txBusy = false, feedbackSeen = false;
  uint16_t sequence = 0;
  HandFeedback feedback = {};
  uint32_t lastAckMs = 0, lastFeedbackMs = 0;
  uint32_t successCount = 0, failureCount = 0, badPayloadCount = 0;
  bool ackFresh() const { return successCount && millis() - lastAckMs < 300; }
  bool pressureFresh() const { return feedbackSeen && millis() - lastFeedbackMs < 300; }
  bool actuatorReady() const { return pressureFresh() && (feedback.flags & 0x20u); }
 private:
  RF24 radio = RF24(RF_CE, RF_CSN, 2000000UL);
  uint32_t lastSendMs = 0, txStartedMs = 0, lastPollUs = 0;
  uint16_t pendingSequence = 0;
  bool feedbackSequenceSeen = false;
  bool pendingSafe = false, syncAllowed = true;
};
#endif
