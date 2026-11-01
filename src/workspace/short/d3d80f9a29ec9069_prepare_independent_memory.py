"""Create simulation-only AMD memory VIP harness; never edit the routed design."""
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'output/pl_reset_closure_20260928'
OUT = ROOT / 'output/pl_ddr_lifecycle_20260928'
SIM = OUT / 'sim'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    SIM.mkdir(parents=True, exist_ok=True)
    original = BASE / 'project/pl_filter_candidate_dma.gen/sources_1/bd/inputs/sim/filter_candidate.v'
    tb_original = BASE / 'inputs/full_chain_reset_tb.sv'
    source = original.read_text()
    edits = []
    responses = 'ARREADY AWREADY WREADY BRESP BVALID RDATA RLAST RRESP RVALID'.split()
    for port in responses + 'ARVALID AWVALID WVALID BREADY RREADY'.split():
        value = '' if port in responses else "1'b0"
        source, count = re.subn(r'\.S_AXI_HP0_' + port + r'\([^)]*\)',
                               '.S_AXI_HP0_' + port + '(' + value + ')', source)
        assert count == 1, (port, count)
        edits.append(port)
    params = dict(C_AXI_PROTOCOL=1, C_AXI_INTERFACE_MODE=2, C_AXI_ADDR_WIDTH=32,
                  C_AXI_WDATA_WIDTH=64, C_AXI_RDATA_WIDTH=64, C_AXI_WID_WIDTH=1,
                  C_AXI_RID_WIDTH=1, C_AXI_AWUSER_WIDTH=0, C_AXI_ARUSER_WIDTH=0,
                  C_AXI_WUSER_WIDTH=0, C_AXI_RUSER_WIDTH=0, C_AXI_BUSER_WIDTH=0,
                  C_AXI_HAS_REGION=0)
    connections = ['.aclk(processing_system7_0_FCLK_CLK0)', ".aclken(1'b1)",
                   '.aresetn(FIXED_IO_0_ps_porb & FIXED_IO_0_ps_srstb)']
    signals = ('AWADDR AWLEN AWSIZE AWBURST AWLOCK AWCACHE AWPROT AWQOS AWVALID AWREADY '
               'WDATA WSTRB WLAST WVALID WREADY BRESP BVALID BREADY '
               'ARADDR ARLEN ARSIZE ARBURST ARLOCK ARCACHE ARPROT ARQOS ARVALID ARREADY '
               'RDATA RRESP RLAST RVALID RREADY').split()
    for signal in signals:
        connections.append(f'.s_axi_{signal.lower()}(pf_memory_M00_AXI_{signal})')
    for signal in 'awid wid arid awregion arregion awuser wuser aruser'.split():
        connections.append(f".s_axi_{signal}(32'b0)")
    for signal in 'bid rid buser ruser'.split():
        connections.append(f'.s_axi_{signal}()')
    instance = '\n  axi_vip_v1_1_22_top #(\n    ' + ',\n    '.join(
        f'.{key}({value})' for key, value in params.items()) + \
        '\n  ) memory_vip (\n    ' + ',\n    '.join(connections) + '\n  );\n'
    source = source.replace('endmodule', instance + 'endmodule', 1)
    (SIM / 'filter_candidate.v').write_text(source)

    tb = tb_original.read_text()
    tb = re.sub(r'  defparam .*afi_rd_max=2000;\n', '', tb)
    tb = re.sub(r'  always @\(posedge `PS.net_sw_clk\) begin.*?\n  end\n', '', tb, flags=re.S)
    tb = tb.replace('  import axi_vip_pkg::*;', '''  import axi_vip_pkg::*;
  axi_slv_mem_agent #(1,32,64,64,1,1,0,0,0,0,0,1,1,1,1,0,1,1,1,1,1,1) mem;''')
    tb = tb.replace('`PS.S_AXI_HP0.slv.', 'mem.')
    tb = tb.replace('read_ready.set_low_time(2000);', 'read_ready.set_low_time(200);')
    tb = tb.replace('    `PS.S_AXI_HP0.set_latency_type(2);', '''    mem=new("independent_memory",dut.memory_vip.IF);
    mem.mem_model.set_inter_beat_gap_delay_policy(XIL_AXI_MEMORY_DELAY_FIXED);
    mem.mem_model.set_inter_beat_gap(100);
    mem.start_slave();''')
    for signal in 'AWID WID BID ARID RID'.split():
        tb = tb.replace('`PS.S_AXI_HP0_' + signal, "1'b0")
    tb = re.sub(r'`PS\.S_AXI_HP0_([A-Z0-9]+)', r'dut.pf_memory_M00_AXI_\1', tb)
    tb = re.sub(r'`PS\.write_mem\(payload,([^,]+),8\);',
                r'mem.mem_model.backdoor_memory_write(\1,payload[63:0]);', tb)
    tb = tb.replace('`PS.read_mem(rx_address+n*8,8,payload);',
                    'payload=0; payload[63:0]=mem.mem_model.backdoor_memory_read(rx_address+n*8);')
    tb = tb.replace('      for(n=0;n<80;n=n+1) begin\n        payload=0;', '''      for(n=0;n<96;n=n+1)
        mem.mem_model.backdoor_memory_write(rx_address-32'd64+n*32'd8,64'hcafe1357face2468);
      for(n=0;n<80;n=n+1) begin
        payload=0;''', 1)
    tb = tb.replace('      mismatches=0; first_bad=-1;', '''      mismatches=0; first_bad=-1;
      if($test$plusargs("corrupt_last_burst"))
        for(n=64;n<80;n=n+1)
          mem.mem_model.backdoor_memory_write(rx_address+n*8,64'hdeadbeefdeadbeef);
      if($test$plusargs("corrupt_rx_guard"))
        mem.mem_model.backdoor_memory_write(rx_address-32'd8,64'h0);
      for(n=0;n<96;n=n+1) begin
        if(n<8 || n>=88)
          if(mem.mem_model.backdoor_memory_read(rx_address-32'd64+n*32'd8)!==64'hcafe1357face2468)
            $fatal(1,"independent memory RX guard overwritten word=%0d",n);
      end''')
    tb = tb.replace('VIP_DDR_MISMATCH', 'INDEPENDENT_MEMORY_MISMATCH').replace(
        'FULL_DDR_GOLDEN_PASS', 'INDEPENDENT_MEMORY_GOLDEN_PASS')
    before = '      repeat(20) @(negedge clk);\n      reset_authorized=0; resets=resets+1;'
    assert tb.count(before) == 1
    tb = tb.replace(before, '''      repeat(20) @(negedge clk);
      for(integer retained=0; retained<80; retained=retained+1)
        if(mem.mem_model.backdoor_memory_read(32'h00201000+retained*32'd8)
           !==expected[80+retained])
          $fatal(1,"PL local reset lost independent memory word=%0d",retained);
      $display("INDEPENDENT_MEMORY_RETAINED_AFTER_PL_RESET words=80");
      reset_authorized=0; resets=resets+1;''')
    assert '`PS.S_AXI_HP0.' not in tb
    (SIM / 'full_chain_reset_tb.sv').write_text(tb)
    old_sim = BASE / 'export/xsim'
    replacements = {original.resolve(): SIM / 'filter_candidate.v',
                    tb_original.resolve(): SIM / 'full_chain_reset_tb.sv'}
    for name in ('vlog.prj', 'vhdl.prj'):
        def normalize(match):
            path = Path(match[1])
            if not path.is_absolute():
                path = (old_sim / path).resolve()
            path = replacements.get(path, path)
            assert path.exists(), path
            return '"' + path.as_posix() + '"'
        (SIM / name).write_text(re.sub(r'"([^"\n]+)"', normalize, (old_sim / name).read_text()))
    for name in ('xsim.ini', 'glbl.v', 'coeff.hex', 'vectors.txt',
                 'sc_xtlm_filter_candidate_pf_axi_sc_0.mem'):
        if (SIM / name).exists():
            assert sha(SIM / name) == sha(old_sim / name), name
        else:
            shutil.copy2(old_sim / name, SIM / name)
    (SIM / 'run.tcl').write_text('run all\nquit\n')
    manifest = dict(original_bd_sim_sha256=sha(original), original_tb_sha256=sha(tb_original),
                    simulation_only_hp0_ports=edits, vip_parameters=params,
                    independent_memory=True, physical_ddr_verified=False,
                    bitstream_generated=False, board_accessed=False)
    (OUT / 'memory_harness_manifest.json').write_text(json.dumps(manifest, indent=2))
    print(SIM)


if __name__ == '__main__':
    main()
