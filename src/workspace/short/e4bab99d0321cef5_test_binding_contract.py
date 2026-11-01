"""Compare the isolated BD with the static device-tree syntax fixture.

Run in WSL with dtc/fdtget installed. This does not inspect the live Z15 or
prove that a bitstream, HWH, and boot device tree match one another.
"""

import json
import subprocess
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
BD = (HERE.parents[1] / "output" / "pl_protocol_explicit_20260928"
      / "project" / "pl_filter_candidate_dma.srcs" / "sources_1" / "bd"
      / "filter_candidate" / "filter_candidate.bd")
NODE = "/amba/dma-owner@40400000"


def fdtget(dtb, kind, property_name):
    return subprocess.check_output(
        ["fdtget", "-t", kind, str(dtb), NODE, property_name],
        text=True,
    ).strip().split()


def main():
    design = json.loads(BD.read_text(encoding="utf-8"))["design"]
    params = design["components"]["pf_dma"]["parameters"]
    expected = {
        "c_include_mm2s": "1", "c_include_s2mm": "1",
        "c_include_sg": "0", "c_addr_width": "32",
        "c_m_axi_mm2s_data_width": "64",
        "c_m_axi_s2mm_data_width": "64",
        "c_m_axis_mm2s_tdata_width": "64",
        "c_s_axis_s2mm_tdata_width": "64",
    }
    for name, value in expected.items():
        assert params[name]["value"] == value, (name, params[name])

    segments = design["addressing"]["/processing_system7_0"][
        "address_spaces"]["Data"]["segments"]
    assert segments["SEG_pf_dma_Reg"]["offset"] == "0x40400000"
    assert segments["SEG_pf_control_Reg"]["offset"] == "0x41200000"
    assert all(segments[name]["range"] == "64K" for name in
               ("SEG_pf_dma_Reg", "SEG_pf_control_Reg"))
    data = design["addressing"]["/pf_dma"]["address_spaces"]
    for direction in ("Data_MM2S", "Data_S2MM"):
        ddr = data[direction]["segments"]["SEG_processing_system7_0_HP0_DDR_LOWOCM"]
        assert (ddr["offset"], ddr["range"]) == ("0x00000000", "1G")

    with tempfile.TemporaryDirectory() as temp_dir:
        dtb = Path(temp_dir) / "binding.dtb"
        subprocess.run(
            ["dtc", "-I", "dts", "-O", "dtb", "-i", str(HERE),
             "-o", str(dtb), str(HERE / "test_dt_binding.dts")],
            check=True,
        )
        assert fdtget(dtb, "x", "reg") == [
            "40400000", "10000", "41200000", "10000"]
        assert fdtget(dtb, "s", "reg-names") == ["dma", "control"]
        assert fdtget(dtb, "s", "compatible") == [
            "guardianloop,z15-filter-dma-owner-v1"]
        assert fdtget(dtb, "x", "guardianloop,abi-version") == ["1"]
        assert fdtget(dtb, "s", "status") == ["disabled"]

    print("GLDMA_BD_DT_BINDING_PASS")


if __name__ == "__main__":
    main()
