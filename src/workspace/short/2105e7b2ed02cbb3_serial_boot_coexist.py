"""One-shot, supervised Z15 serial boot into the already-reviewed coexistence DTB.

The only persistent change is stopping the Cyton service before reboot. U-Boot
environment, SD boot files and QSPI are never written. A failed check leaves
the board at the U-Boot prompt for manual recovery.
"""

import argparse
import sys
import time
from pathlib import Path

import serial


APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from run_soak_stage import connect, command  # noqa: E402
from deploy_ssvep_rail_coalesce import sudo  # noqa: E402


BOOT_HASHES = {
    "/boot/image.ub": "27ee421d07d70f972e8a3bca96e1bc7810e847be2da2360aa5c11d36c93e89b2",
    "/boot/boot.scr": "21d2ef676010175446757451450fffc6c19096f9c2854c5c784a9e918676fb63",
    "/boot/guardianloop_coexist_20260929.dtb": "4f73625b330bf07367c64a8c418d5716776ca092551ef5eb323eca4a0146f47c",
}


def receive_until(port, marker, seconds):
    deadline = time.monotonic() + seconds
    buffer = bytearray()
    while time.monotonic() < deadline:
        data = port.read(512)
        if data:
            buffer.extend(data)
            if marker in buffer:
                return bytes(buffer)
            if len(buffer) > 50000:
                del buffer[:-25000]
    raise TimeoutError(f"Serial did not show {marker!r}; tail={buffer[-1000:]!r}")


def command_at_prompt(port, line, expected, seconds=12):
    port.reset_input_buffer()
    port.write(line.encode("ascii") + b"\r")
    port.flush()
    output = receive_until(port, b"Zynq>", seconds)
    text = output.decode(errors="replace")
    print(f"UBOOT {line}\n{text[-1000:]}", flush=True)
    if expected not in text:
        raise RuntimeError(f"U-Boot response for {line!r} omitted {expected!r}")
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Confirmed Z15 console COM port")
    args = parser.parse_args()
    port = serial.Serial(port=None, baudrate=115200, timeout=0.05, write_timeout=1)
    port.dtr = False
    port.rts = False
    port.port = args.port
    port.open()
    try:
        port.reset_input_buffer()
        port.write(b"\r")
        port.flush()
        identify = receive_until(port, b"xilinx@pynq:", 4)
        print("SERIAL_Z15_LINUX_IDENTIFIED " + identify.decode(errors="replace")[-160:], flush=True)
        client = connect()
        try:
            if command(client, "uname -r").strip() != "5.4.0-xilinx-v2020.2":
                raise RuntimeError("Kernel mismatch")
            deadline = time.monotonic() + 60
            while command(client, "findmnt -n /boot >/dev/null && test -f /boot/image.ub "
                                  "&& echo BOOT_READY || true").strip() != "BOOT_READY":
                if time.monotonic() >= deadline:
                    raise RuntimeError("Boot partition did not mount; no reboot requested")
                time.sleep(1)
            for path, expected in BOOT_HASHES.items():
                actual = command(client, "sha256sum " + path).split()[0]
                if actual != expected:
                    raise RuntimeError(f"Boot preflight hash mismatch: {path}")
            if command(client, "lsmod | grep '^gldma_owner ' || true").strip():
                raise RuntimeError("DMA owner is already loaded; do not reprogram")
            sudo(client, "systemctl stop guardianloop-cyton.service")
            if command(client, "systemctl is-active guardianloop-cyton.service || true").strip() != "inactive":
                raise RuntimeError("Formal service did not stop")
            stdin, _, _ = client.exec_command("sudo -S -p '' systemctl reboot", timeout=5)
            stdin.write("xilinx\n")
            stdin.flush()
            print("REBOOT_SENT_SERIAL_WATCHING", flush=True)
        finally:
            client.close()
        receive_until(port, b"Hit any key to stop autoboot", 40)
        for _ in range(4):
            port.write(b"\r")
            port.flush()
            time.sleep(0.12)
        receive_until(port, b"Zynq>", 5)
        print("UBOOT_STOPPED", flush=True)
        command_at_prompt(port, "mmc dev 0", "mmc0 is current device")
        command_at_prompt(port, "fatload mmc 0:1 0x10000000 image.ub", "5889672 bytes read")
        command_at_prompt(port, "fatload mmc 0:1 0x20000000 guardianloop_coexist_20260929.dtb",
                          "17337 bytes read")
        command_at_prompt(port, "fdt addr 0x20000000", "Zynq>")
        node = command_at_prompt(port, "fdt print /amba/dma-owner@40410000",
                                 'compatible = "guardianloop,z15-filter-dma-owner-v1"')
        if 'reg = <0x40410000 0x00010000 0x41200000 0x00010000>' not in node:
            raise RuntimeError("Candidate DMA/control register map mismatch")
        port.reset_input_buffer()
        port.write(b"bootm 0x10000000:kernel@0 - 0x20000000\r")
        port.flush()
        output = receive_until(port, b"Booting using the fdt blob at 0x20000000", 20)
        print("CANDIDATE_DTB_BOOTING " + output.decode(errors="replace")[-500:], flush=True)
    finally:
        port.close()


if __name__ == "__main__":
    main()
