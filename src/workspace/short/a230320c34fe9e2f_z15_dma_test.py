from pathlib import Path
from time import monotonic

import numpy as np
from pynq import Overlay, allocate


HERE = Path(__file__).resolve().parent
LENGTHS = (16, 256, 2048)


def main():
    overlay = Overlay(str(HERE / "z15_dma_loopback.bit"), download=True)
    dma = overlay.axi_dma_0
    print(f"overlay_loaded={overlay.is_loaded()}", flush=True)
    print(f"dma_physical_address=0x{dma.mmio.base_addr:08X}", flush=True)

    for length in LENGTHS:
        src = allocate(shape=(length,), dtype=np.uint32)
        dst = allocate(shape=(length,), dtype=np.uint32)
        try:
            src[:] = (np.arange(length, dtype=np.uint32) * np.uint32(17)) ^ np.uint32(0x5A5A1234)
            dst[:] = np.uint32(0xDEADBEEF)
            src.flush()
            dst.flush()

            start = monotonic()
            dma.recvchannel.transfer(dst)
            dma.sendchannel.transfer(src)
            dma.sendchannel.wait()
            dma.recvchannel.wait()
            dst.invalidate()
            elapsed_ms = (monotonic() - start) * 1000
            if not np.array_equal(src, dst):
                mismatch = np.flatnonzero(src != dst)
                first = int(mismatch[0])
                raise RuntimeError(
                    f"DMA mismatch at index {first}: src=0x{int(src[first]):08X}, "
                    f"dst=0x{int(dst[first]):08X}"
                )
            print(
                f"words={length} bytes={src.nbytes} "
                f"src_phys=0x{src.physical_address:08X} "
                f"dst_phys=0x{dst.physical_address:08X} "
                f"elapsed_ms={elapsed_ms:.2f} equal=True",
                flush=True,
            )
        finally:
            src.close()
            dst.close()

    print("Z15_PYNQ_DMA_LOOPBACK_OK", flush=True)


if __name__ == "__main__":
    main()
