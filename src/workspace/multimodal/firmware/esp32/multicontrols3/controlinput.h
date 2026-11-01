#ifndef CONTROL_INPUT_H
#define CONTROL_INPUT_H
#include <stdint.h>
#include <math.h>

struct GripGate {
    bool gripped = false;
    bool armed = false;
    uint8_t highCount = 0, lowCount = 0;
    void reset() { gripped = armed = false; highCount = lowCount = 0; }
    void update(float strength, bool valid) {
        if (!valid) { reset(); return; }
        if (strength >= 100.0f) {
            lowCount = 0;
            if (highCount < 2) ++highCount;
            if (armed && highCount >= 2) gripped = true;
        } else if (strength <= 50.0f) {
            highCount = 0;
            if (lowCount < 2) ++lowCount;
            if (lowCount >= 2) { gripped = false; armed = true; }
        } else { highCount = lowCount = 0; }
    }
};

// Temporary electrode-contact switch. This is not a muscle-strength classifier.
// Two complete 100 ms windows debounce each edge; a release must precede a press.
struct ContactGate {
    static constexpr float PRESS_STRENGTH = 500.0f;
    static constexpr float RELEASE_STRENGTH = 50.0f;
    bool gripped = false;
    bool armed = false;
    uint8_t pressCount = 0, releaseCount = 0;
    void reset() { gripped = armed = false; pressCount = releaseCount = 0; }
    void update(float strength, bool worn, bool valid) {
        if (!valid || !isfinite(strength)) { reset(); return; }
        if (worn && strength >= PRESS_STRENGTH) {
            releaseCount = 0;
            if (pressCount < 2) ++pressCount;
            if (armed && pressCount >= 2) gripped = true;
        } else if (!worn || strength <= RELEASE_STRENGTH) {
            pressCount = 0;
            if (releaseCount < 2) ++releaseCount;
            if (releaseCount >= 2) { gripped = false; armed = true; }
        } else { pressCount = releaseCount = 0; }
    }
};

struct TurnGate {
    bool armed = false;
    int candidate = 0;
    uint32_t candidateSince = 0, neutralSince = 0;
    bool neutralTiming = false;
    void reset() { armed = false; candidate = 0; neutralTiming = false; }
    int update(float yaw, uint32_t now, bool valid) {
        if (!valid) { reset(); return 0; }
        if (fabsf(yaw) <= 10.0f) {
            candidate = 0;
            if (!neutralTiming) { neutralSince = now; neutralTiming = true; }
            if ((uint32_t)(now - neutralSince) >= 200) armed = true;
            return 0;
        }
        neutralTiming = false;
        if (!armed) return 0;
        int direction = yaw >= 25.0f ? 1 : (yaw <= -25.0f ? -1 : 0);
        if (!direction) { candidate = 0; return 0; }
        if (direction != candidate) { candidate = direction; candidateSince = now; }
        if ((uint32_t)(now - candidateSince) < 150) return 0;
        armed = false; candidate = 0;
        return direction; // +1 = left, -1 = right; return to neutral to rearm.
    }
};
#endif
