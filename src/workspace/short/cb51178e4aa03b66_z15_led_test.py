from pathlib import Path
from time import sleep

from pynq import Overlay


HERE = Path(__file__).resolve().parent
BITSTREAM = HERE / "z15_led.bit"


def main():
    overlay = Overlay(str(BITSTREAM), download=True)
    gpio = overlay.axi_gpio_0

    print(f"overlay_loaded={overlay.is_loaded()}")
    print(f"gpio_physical_address=0x{gpio.mmio.base_addr:08X}")

    for cycle in range(2):
        for value in (0b00, 0b01, 0b10, 0b11):
            gpio.write(0x0, value)
            observed = gpio.read(0x0) & 0b11
            print(f"cycle={cycle + 1} write={value:02b} read={observed:02b}")
            if observed != value:
                raise RuntimeError(f"LED GPIO mismatch: wrote {value:02b}, read {observed:02b}")
            sleep(0.5)

    gpio.write(0x0, 0b01)
    print("final_led_pattern=01")
    print("Z15_PYNQ_LED_TEST_OK")


if __name__ == "__main__":
    main()
