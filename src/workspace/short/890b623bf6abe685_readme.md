# Z15 PYNQ AXI DMA loopback

This project builds a standalone PL overlay for the ALIENTEK Z15 (XC7Z015)
using Vivado 2025.2. It does not alter the earlier GPIO, LED, or key overlays.

## Data path

PS DDR -> AXI DMA MM2S -> PL AXI-Stream wire -> AXI DMA S2MM -> PS DDR.
The PS controls DMA registers through M_AXI_GP0 at `0x40400000`; both DMA
memory masters reach DDR through S_AXI_HP0. AXI DMA is in simple (non-SG)
mode. The stream connection carries TLAST to the receive channel.

The Z15 vendor PS7 design specifies 1 GiB of DDR (`0x00000000` through
`0x3FFFFFFF`). This matters because PYNQ CMA buffers on the tested board
were allocated near `0x38046000`, outside Vivado's default 512 MiB map.
The overlay build uses the vendor DDR part and 1 GiB address range.

## Build and deploy

Run `build_overlay.tcl` in Vivado batch mode. The resulting
`output/z15_dma_loopback.bit` and `.hwh` are paired files; deploy both.
Run `deploy_and_test.py` with Windows Python/Paramiko to upload both files,
the test script, and the Notebook to
`/home/xilinx/jupyter_notebooks/z15_dma/` and run a bounded board test.

Open `http://192.168.2.99:9090/notebooks/z15_dma/z15_dma.ipynb` in the
board's Jupyter server and use **Cell -> Run All**. Loading this overlay
replaces the previous PL configuration, so the key/LED overlay stops being
active until it is loaded again.

## Board result (2026-09-15)

The test ran under PYNQ 2.7 on the physical Z15 and exited with code 0:

```text
overlay_loaded=True
dma_physical_address=0x40400000
words=16 bytes=64 ... equal=True
words=256 bytes=1024 ... equal=True
words=2048 bytes=8192 ... equal=True
Z15_PYNQ_DMA_LOOPBACK_OK
```

`z15_dma_test.py` flushes source and destination buffers before transfer,
starts S2MM before MM2S, waits for both channels, invalidates the destination
cache, and then compares every 32-bit word. The deployment test is wrapped
in a 25-second timeout so a stalled DMA cannot hang the remote command
indefinitely.
