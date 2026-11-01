#ifndef WC_FIRMWARE_CONFIG_H
#define WC_FIRMWARE_CONFIG_H

#if __has_include("config_private.h")
#include "config_private.h"
#endif

/* Default build does not start Wi-Fi and never configures/writes motor GPIO. */
#ifndef WC_ENABLE_MOTOR_GPIO
#define WC_ENABLE_MOTOR_GPIO 0
#endif
#ifndef WC_GPIO_BINDING_VERIFIED
#define WC_GPIO_BINDING_VERIFIED 0
#endif
#ifndef WC_INDEPENDENT_ESTOP_VERIFIED
#define WC_INDEPENDENT_ESTOP_VERIFIED 0
#endif

/* Leave credentials blank in shared source. Configure privately before a disconnected-motor bench test. */
#ifndef WC_STA_SSID
#define WC_STA_SSID ""
#endif
#ifndef WC_STA_PASSWORD
#define WC_STA_PASSWORD ""
#endif
#ifndef WC_AP_SSID
#define WC_AP_SSID "GuardianLoop-Wheelchair"
#endif
#ifndef WC_AP_PASSWORD
#define WC_AP_PASSWORD ""
#endif
#ifndef WC_AUTH_TOKEN
#define WC_AUTH_TOKEN ""
#endif

#if WC_ENABLE_MOTOR_GPIO && (!WC_GPIO_BINDING_VERIFIED || !WC_INDEPENDENT_ESTOP_VERIFIED)
#error "Motor GPIO requires verified wiring/STOP levels and independent hardware emergency stop."
#endif

#endif
