"""Assert that the isolated coexistence BD preserved the production contract."""

import argparse
import hashlib
import json
from pathlib import Path


BASE_CELLS = {
    "processing_system7_0", "rst_ps7_0_50M", "axi_smc_0", "axi_smc_mem_0",
    "axi_dma_0", "guardianloop_regs_v0_0", "guardianloop_eeg_quality_v0_0",
    "guardianloop_eeg_de_accel_v0_0", "guardianloop_hgb_accel_v0_0",
}
NEW_CELLS = {"pf_filter", "pf_dma", "pf_control", "pf_read_pc", "pf_write_pc"}
NEW_STREAMS = {
    frozenset(("pf_dma/M_AXIS_MM2S", "pf_filter/s_axis")),
    frozenset(("pf_filter/m_axis", "pf_dma/S_AXIS_S2MM")),
    frozenset(("pf_dma/M_AXI_MM2S", "pf_read_pc/S_AXI")),
    frozenset(("pf_dma/M_AXI_S2MM", "pf_write_pc/S_AXI")),
    frozenset(("pf_read_pc/M_AXI", "axi_smc_mem_0/S01_AXI")),
    frozenset(("pf_write_pc/M_AXI", "axi_smc_mem_0/S02_AXI")),
    frozenset(("axi_smc_0/M05_AXI", "pf_dma/S_AXI_LITE")),
    frozenset(("axi_smc_0/M06_AXI", "pf_control/S_AXI")),
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))["design"]


def values(component):
    return {name: entry.get("value") for name, entry in component.get("parameters", {}).items()}


def nets(design, kind):
    field = "interface_ports" if kind == "interface_nets" else "ports"
    return {name: set(entry[field]) for name, entry in design[kind].items()}


def segments(design, owner, space):
    return design["addressing"][owner]["address_spaces"][space]["segments"]


def size(value):
    if isinstance(value, str) and value[-1] in "KMG":
        return int(value[:-1]) * (1024 ** ("KMG".index(value[-1]) + 1))
    return int(value, 0)


def audit(source_path, candidate_path, report_path, direct_smartconnect=False):
    expected_new_cells = NEW_CELLS - {"pf_read_pc", "pf_write_pc"} if direct_smartconnect else NEW_CELLS
    expected_streams = (
        NEW_STREAMS - {
            frozenset(("pf_dma/M_AXI_MM2S", "pf_read_pc/S_AXI")),
            frozenset(("pf_dma/M_AXI_S2MM", "pf_write_pc/S_AXI")),
            frozenset(("pf_read_pc/M_AXI", "axi_smc_mem_0/S01_AXI")),
            frozenset(("pf_write_pc/M_AXI", "axi_smc_mem_0/S02_AXI")),
        } | {
            frozenset(("pf_dma/M_AXI_MM2S", "axi_smc_mem_0/S01_AXI")),
            frozenset(("pf_dma/M_AXI_S2MM", "axi_smc_mem_0/S02_AXI")),
        }
        if direct_smartconnect else NEW_STREAMS
    )
    old, new = load(source_path), load(candidate_path)
    assert old["design_info"]["device"] == new["design_info"]["device"] == "xc7z015clg485-2"
    old_cells = set(old["design_tree"])
    new_cells = set(new["design_tree"])
    assert old_cells == BASE_CELLS, old_cells
    assert new_cells == BASE_CELLS | expected_new_cells, new_cells

    changed_parameters = {}
    for cell in BASE_CELLS:
        before = values(old["components"][cell])
        after = values(new["components"][cell])
        changed = {name: (before.get(name), after.get(name)) for name in before.keys() | after.keys()
                   if before.get(name) != after.get(name)}
        if changed:
            changed_parameters[cell] = changed
    assert changed_parameters == {
        "axi_smc_0": {"NUM_MI": ("5", "7")},
        "axi_smc_mem_0": {"NUM_SI": ("1", "3")},
    }, changed_parameters

    for kind in ("interface_nets", "nets"):
        old_nets, new_nets = nets(old, kind), nets(new, kind)
        for name, endpoints in old_nets.items():
            assert name in new_nets and endpoints <= new_nets[name], (kind, name, endpoints)
    new_streams = {frozenset(endpoints) for endpoints in nets(new, "interface_nets").values()}
    assert expected_streams <= new_streams
    new_wires = list(nets(new, "nets").values())
    for pair in (
        {"pf_control/gpio_io_o", "pf_filter/control_word"},
        {"pf_filter/status_word", "pf_control/gpio2_io_i"},
    ):
        assert any(pair <= wire for wire in new_wires), pair
    for pin, clock in (
        ("pf_filter/aclk", "processing_system7_0/FCLK_CLK0"),
        ("pf_dma/m_axi_mm2s_aclk", "processing_system7_0/FCLK_CLK0"),
        ("pf_dma/m_axi_s2mm_aclk", "processing_system7_0/FCLK_CLK0"),
        ("pf_filter/aresetn", "rst_ps7_0_50M/peripheral_aresetn"),
        ("pf_dma/axi_resetn", "rst_ps7_0_50M/peripheral_aresetn"),
    ):
        assert any({pin, clock} <= wire for wire in new_wires), (pin, clock)

    before = segments(old, "/processing_system7_0", "Data")
    after = segments(new, "/processing_system7_0", "Data")
    assert set(after) == set(before) | {"SEG_pf_dma_Reg", "SEG_pf_control_Reg"}
    assert all(after[name] == segment for name, segment in before.items())
    intervals = []
    for name, entry in after.items():
        start = int(entry["offset"], 0)
        intervals.append((start, start + size(entry["range"]), name))
    intervals.sort()
    assert all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])), intervals
    for owner in ("/pf_dma", "/axi_dma_0"):
        spaces = new["addressing"][owner]["address_spaces"]
        for space in spaces.values():
            ddr = space["segments"]["SEG_processing_system7_0_HP0_DDR_LOWOCM"]
            assert ddr["offset"] in ("0x00000000", "0x0") and ddr["range"] == "1G"
    if not direct_smartconnect:
        for name in ("pf_read_pc", "pf_write_pc"):
            p = values(new["components"][name])
            assert (p["SI_PROTOCOL"], p["MI_PROTOCOL"], p["DATA_WIDTH"]) == ("AXI4", "AXI3", "64")
    dma = values(new["components"]["pf_dma"])
    assert dma["c_include_sg"] == "0" and dma["c_include_s2mm"] == "1"
    assert dma["c_m_axis_mm2s_tdata_width"] == dma["c_s_axis_s2mm_tdata_width"] == "64"

    report = {
        "status": "BD_STRUCTURE_PASS_ONLY",
        "source_bd_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "candidate_bd_sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        "device": "xc7z015clg485-2", "production_cells_preserved": sorted(BASE_CELLS),
        "new_cells": sorted(expected_new_cells), "changed_production_parameters": changed_parameters,
        "production_addresses_preserved": True,
        "new_addresses": {name: after[name] for name in ("SEG_pf_dma_Reg", "SEG_pf_control_Reg")},
        "axi_stream_links_checked": len(expected_streams),
        "limits": ["No synthesis, implementation, timing, DRC or bitstream verification",
                   "No runtime driver/device-tree integration or fault-recovery measurement"],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--direct-smartconnect", action="store_true")
    args = parser.parse_args()
    audit(args.source, args.candidate, args.report, args.direct_smartconnect)
