from pathlib import Path

import numpy as np
from pynq import Overlay, allocate


HERE = Path(__file__).resolve().parent


def main():
    overlay = Overlay(str(HERE / "z15_dma_add1.bit"), download=True)
    dma = overlay.axi_dma_0
    print(f"overlay_loaded={overlay.is_loaded()}", flush=True)
    src = allocate(shape=(256,), dtype=np.uint32)
    dst = allocate(shape=(256,), dtype=np.uint32)
    try:
        src[:] = (np.arange(256, dtype=np.uint32) * np.uint32(17)) ^ np.uint32(0x5A5A1234)
        src[:4] = [0, 1, 0x7FFFFFFF, 0xFFFFFFFF]
        dst[:] = np.uint32(0xDEADBEEF)
        src.flush()
        dst.flush()
        dma.recvchannel.transfer(dst)
        dma.sendchannel.transfer(src)
        dma.sendchannel.wait()
        dma.recvchannel.wait()
        dst.invalidate()
        expected = src + np.uint32(1)
        if not np.array_equal(dst, expected):
            mismatch = np.flatnonzero(dst != expected)
            i = int(mismatch[0])
            raise RuntimeError(
                f"Mismatch at {i}: input=0x{int(src[i]):08X}, "
                f"expected=0x{int(expected[i]):08X}, got=0x{int(dst[i]):08X}"
            )
        print("words=256 bytes=1024 all_plus_one=True", flush=True)
        print(f"overflow_0xFFFFFFFF_to_0x{int(dst[3]):08X}", flush=True)
        print("Z15_PYNQ_PL_ADD1_OK", flush=True)
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    main()
