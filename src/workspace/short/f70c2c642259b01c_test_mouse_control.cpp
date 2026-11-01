#include <stdio.h>
#include "../firmware/guardianloop_eye_mouse/control_selftest.h"

int main() {
  const char *failure = eye_mouse_test::run();
  if (failure) {
    puts(failure);
    return 1;
  }
  puts("PASS: shared controller and HID descriptor checks");
  return 0;
}
