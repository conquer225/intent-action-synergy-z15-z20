from pathlib import Path

from pynq import Overlay


HERE = Path(__file__).resolve().parent
BITSTREAM = HERE / "z15_smoke.bit"
TEST_VALUES = (0x00000000, 0x12345678, 0xA5A55A5A, 0xFFFFFFFF)


def main():
    overlay = Overlay(str(BITSTREAM), download=True)
    gpio = overlay.axi_gpio_0

    print(f"bitstream={BITSTREAM}")
    print(f"overlay_loaded={overlay.is_loaded()}")
    print(f"gpio_physical_address=0x{gpio.mmio.base_addr:08X}")

    for value in TEST_VALUES:
        gpio.write(0x0, value)
        observed = gpio.read(0x0)
        print(f"write=0x{value:08X} read=0x{observed:08X}")
        if observed != value:
            raise RuntimeError(
                f"AXI GPIO readback mismatch: wrote 0x{value:08X}, "
                f"read 0x{observed:08X}"
            )

    print("Z15_PYNQ_SMOKE_TEST_OK")


if __name__ == "__main__":
    main()
