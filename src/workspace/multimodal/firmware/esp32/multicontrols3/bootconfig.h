#pragma once
// Default firmware starts local contact/MPU control after readiness checks.
// Host tests of the manual commissioning workflow override this to 0.
#ifndef MULTICONTROL_AUTO_START
#define MULTICONTROL_AUTO_START 1
#endif
constexpr bool BOOT_AUTO_START = MULTICONTROL_AUTO_START != 0;
