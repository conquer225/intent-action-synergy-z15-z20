# Z15 PYNQ smoke-test overlay

This project targets the ALIENTEK Z15 module (`xc7z015clg485-2`) and verifies
the complete PYNQ control path without using any external PL pins:

`Python -> PYNQ Overlay -> PS M_AXI_GP0 -> AXI interconnect -> AXI GPIO`

## Build

Run Vivado 2025.2 in batch mode:

```powershell
& "D:\ruanjian\2025.2\Vivado\bin\vivado.bat" -mode batch `
  -source "D:\ican\codex_project\pynq_z15_smoke_overlay\build_overlay.tcl"
```

Successful output is written to `output/z15_smoke.bit` and
`output/z15_smoke.hwh`.

## Board test

Copy these three files to the same directory on the PYNQ board:

- `z15_smoke.bit`
- `z15_smoke.hwh`
- `z15_smoke_test.py`

Run the test from a root-owned Jupyter kernel or with `sudo`:

```bash
python3 z15_smoke_test.py
```

The final line must be `Z15_PYNQ_SMOKE_TEST_OK`.
