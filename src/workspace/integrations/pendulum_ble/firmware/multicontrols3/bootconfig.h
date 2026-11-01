#pragma once
// BLE pendulum requires explicit enable. Preserve the prior hand-only startup.
#ifndef MULTICONTROL_AUTO_START
#define MULTICONTROL_AUTO_START 0
#endif
constexpr bool BOOT_AUTO_START = MULTICONTROL_AUTO_START != 0;
#ifndef MULTICONTROL_HAND_AUTO_START
#define MULTICONTROL_HAND_AUTO_START 1
#endif
constexpr bool BOOT_HAND_AUTO_START = MULTICONTROL_HAND_AUTO_START != 0;
