from pathlib import Path
from time import sleep

from pynq import Overlay


HERE = Path(__file__).resolve().parent


def main():
    overlay = Overlay(str(HERE / "z15_key_led.bit"), download=True)
    gpio = overlay.axi_gpio_0
    print(f"overlay_loaded={overlay.is_loaded()}")
    print(f"gpio_physical_address=0x{gpio.mmio.base_addr:08X}")
    print("gpio_channels=2 (LED output, key input)")

    # Channel 1 outputs drive the two LEDs; channel 2 inputs sample the keys.
    gpio.mmio.write(0x04, 0b00)
    gpio.mmio.write(0x0C, 0b11)
    for value in (0b00, 0b01, 0b10, 0b11):
        gpio.mmio.write(0x00, value)
        observed = gpio.mmio.read(0x00) & 0b11
        keys = gpio.mmio.read(0x08) & 0b11
        print(f"led_write={value:02b} led_read={observed:02b} key_raw={keys:02b}")
        if observed != value:
            raise RuntimeError(f"LED register readback mismatch: {observed:02b} != {value:02b}")
        sleep(0.25)

    gpio.mmio.write(0x00, 0b01)
    print("Z15_PYNQ_KEY_LED_REGISTER_TEST_OK")
    print("Press/release behavior requires a human-operated key check in the notebook.")


if __name__ == "__main__":
    main()
