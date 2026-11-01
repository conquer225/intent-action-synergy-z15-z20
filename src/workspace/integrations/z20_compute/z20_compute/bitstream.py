"""Convert Vivado raw .bin data to the byte order expected by Zynq FPGA Manager."""

import argparse
from pathlib import Path


_VIVADO_SYNC = bytes.fromhex("aa995566")
_MANAGER_SYNC = bytes.fromhex("665599aa")


def to_fpga_manager_bytes(raw):
    """Reverse the bytes within each 32-bit configuration word."""
    if len(raw) % 4:
        raise ValueError("configuration data must contain complete 32-bit words")
    sync_offset = raw.find(_VIVADO_SYNC)
    if sync_offset < 0 or sync_offset % 4:
        raise ValueError("aligned Vivado sync word not found")
    result = bytearray(len(raw))
    for offset in range(0, len(raw), 4):
        result[offset:offset + 4] = raw[offset:offset + 4][::-1]
    if result.find(_MANAGER_SYNC) != sync_offset:
        raise ValueError("FPGA Manager sync word missing after conversion")
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    args.target.write_bytes(to_fpga_manager_bytes(args.source.read_bytes()))


if __name__ == "__main__":
    main()
