#ifndef PENDULUM_C3_WIFI_CONFIG_H
#define PENDULUM_C3_WIFI_CONFIG_H
// Copy to WifiConfig.h and set a private WPA2 password of 8 to 63 bytes.
// Empty passwords deliberately prevent AP startup.
constexpr char AP_SSID[] = "NaoDun-Control";
constexpr char AP_PASSWORD[] = "";
constexpr char CONTROLLER_DEVICE_NAME[] = "pendulum-bridge-c3";
#endif
