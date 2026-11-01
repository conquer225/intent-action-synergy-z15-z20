#include "GloveRadio.h"

bool GloveRadio::begin() {
  txBusy = feedbackSeen = false;
  feedbackSequenceSeen=false;
  syncAllowed=true;
  successCount = failureCount = badPayloadCount = 0;
  lastAckMs = lastFeedbackMs = lastSendMs = 0;
  const uint8_t address[6] = "00001";
  SPI.begin(RF_SCK, RF_MISO, RF_MOSI, RF_CSN);
  ready = radio.begin(&SPI);
  if (!ready) return false;
  radio.setChannel(115);
  radio.setDataRate(RF24_1MBPS);
  radio.setPALevel(RF24_PA_LOW);
  radio.setCRCLength(RF24_CRC_16);
  radio.setRetries(5, 15);
  radio.setAutoAck(true);
  radio.enableAckPayload();
  radio.openWritingPipe(address);
  radio.stopListening();
  radio.flush_tx(); radio.flush_rx();
  bool ok, failed, received;
  radio.whatHappened(ok, failed, received);
  return true;
}

void GloveRadio::cancel() {
  txBusy=false; feedbackSeen=false;
  syncAllowed=true;
  if (ready) {
    radio.stopListening(); radio.flush_tx(); radio.flush_rx();
    bool ok=false, failed=false, received=false;
    radio.whatHappened(ok,failed,received);
  }
  // Safe-open can be sent immediately; do not wait for the previous cadence.
  lastSendMs=millis()-20u;
}

void GloveRadio::tick(bool enabled, const int16_t *angles) {
  if (!ready) return;
  uint32_t now = millis();
  if (txBusy && (uint32_t)(micros() - lastPollUs) >= 1000) {
    lastPollUs = micros();
    bool ok = false, failed = false, received = false;
    radio.whatHappened(ok, failed, received);
    if (ok) { ++successCount; lastAckMs = now; }
    if (received || radio.available()) {
      // One transmission is in flight. Drain all ACK payloads without blocking.
      for (uint8_t n = 0; n < 3 && radio.available(); ++n) {
        uint8_t size = radio.getDynamicPayloadSize();
        if (size != HAND_FEEDBACK_SIZE) {
          ++badPayloadCount; feedbackSeen=false; radio.flush_rx(); break;
        }
        uint8_t bytes[HAND_FEEDBACK_SIZE];
        radio.read(bytes, sizeof(bytes));
        HandFeedback decoded;
        if (decodeFeedback(bytes, sizeof(bytes), decoded) &&
            (uint16_t)(pendingSequence - decoded.sequence) <= 8) {
          uint16_t delta=(uint16_t)(decoded.sequence-feedback.sequence);
          if (!feedbackSequenceSeen || (delta && delta<0x8000u)) {
            feedback=decoded; feedbackSeen=feedbackSequenceSeen=true; lastFeedbackMs=now;
          }
          syncAllowed=false;
        } else if (decodeFeedback(bytes,sizeof(bytes),decoded) && pendingSafe && syncAllowed &&
                   uint16_t(decoded.sequence-pendingSequence)<0x8000u) {
          // Learn only an ahead receiver counter using OPEN. A restarted Nano
          // queues its old ACK before accepting our current packet, so rewinding
          // to that behind counter would strand both peers on different epochs.
          // This ACK is not pressure evidence; a subsequent new ACK is required.
          sequence=decoded.sequence; feedback=decoded; feedbackSeen=false;
          feedbackSequenceSeen=true; syncAllowed=false;
        } else { ++badPayloadCount; feedbackSeen=false; }
      }
    }
    if (failed || (!ok && (uint32_t)(now - txStartedMs) > 80)) {
      ++failureCount; radio.flush_tx(); txBusy = false;
    } else if (ok) txBusy = false;
  }
  if (!enabled || txBusy || (uint32_t)(now - lastSendMs) < 20) return;
  lastSendMs = now;
  uint8_t bytes[HAND_CONTROL_SIZE];
  pendingSequence = ++sequence;
  pendingSafe = poseMatchesSafe(angles);
  encodeHand(pendingSequence, angles, bytes);
  txStartedMs = now; lastPollUs = micros();
  // startWrite pulses CE and returns; retries run in the nRF hardware.
  txBusy = radio.startWrite(bytes, sizeof(bytes), false);
  if (!txBusy) { ++failureCount; radio.flush_tx(); }
}
