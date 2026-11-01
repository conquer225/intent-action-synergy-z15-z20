#ifndef PENDULUM_C3_WIFI_CONFIG_H
#define PENDULUM_C3_WIFI_CONFIG_H
constexpr char AP_SSID[] = "Test-Control";
#ifdef TEST_C3_EMPTY_PASSWORD
constexpr char AP_PASSWORD[] = "";
#else
constexpr char AP_PASSWORD[] = "test-only-12345";
#endif
constexpr char CONTROLLER_DEVICE_NAME[] = "pendulum-bridge-c3";
#endif
