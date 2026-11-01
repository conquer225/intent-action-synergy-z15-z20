`timescale 1ns/1ps

// Isolated vendor-IP co-sim. The AXI3 memory model is deliberately not reset
// with the PL, modelling an outstanding PS/DDR read across a PL reset.
module vendor_dma_reset_tb;
  reg clk = 0;
  always #10 clk = ~clk;
  reg resetn = 0;
  reg awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready_lite = 1;
  reg [9:0] awaddr = 0, araddr = 0;
  reg [31:0] wdata = 0;
  wire awready, wready, bvalid, arready, rvalid_lite;
  wire [1:0] bresp, rresp_lite;
  wire [31:0] rdata_lite;

  wire [31:0] dma_araddr;
  wire [7:0] dma_arlen;
  wire [2:0] dma_arsize, dma_arprot;
  wire [1:0] dma_arburst;
  wire [3:0] dma_arcache;
  wire dma_arvalid, dma_arready;
  wire [63:0] dma_rdata;
  wire [1:0] dma_rresp;
  wire dma_rlast, dma_rvalid, dma_rready;
  wire [63:0] tdata;
  wire [7:0] tkeep;
  wire tvalid, tlast;
  reg tready = 1;
  wire [31:0] mem_araddr;
  wire [3:0] mem_arlen;
  wire [2:0] mem_arsize, mem_arprot;
  wire [1:0] mem_arburst, mem_arlock;
  wire [3:0] mem_arcache, mem_arqos;
  wire mem_arvalid, mem_rready;
  reg mem_active = 0, mem_stall = 0;
  reg flush_memory_on_reset = 0;
  wire mem_arready = !mem_active;
  reg [63:0] mem_rdata = 0;
  reg [1:0] mem_rresp = 0;
  reg mem_rlast = 0, mem_rvalid = 0;
  wire [31:0] dma_awaddr;
  wire [7:0] dma_awlen, dma_wstrb, axis_keep;
  wire [2:0] dma_awsize, dma_awprot;
  wire [1:0] dma_awburst, dma_bresp;
  wire [3:0] dma_awcache;
  wire dma_awvalid, dma_awready, dma_wlast, dma_wvalid, dma_wready;
  wire dma_bvalid, dma_bready, axis_valid, axis_last, axis_ready;
  wire [63:0] dma_wdata, axis_data;

  filter_candidate_pf_dma_0 dma (
    .s_axi_lite_aclk(clk), .m_axi_mm2s_aclk(clk), .m_axi_s2mm_aclk(clk), .axi_resetn(resetn),
    .s_axi_lite_awvalid(awvalid), .s_axi_lite_awready(awready), .s_axi_lite_awaddr(awaddr),
    .s_axi_lite_wvalid(wvalid), .s_axi_lite_wready(wready), .s_axi_lite_wdata(wdata),
    .s_axi_lite_bresp(bresp), .s_axi_lite_bvalid(bvalid), .s_axi_lite_bready(bready),
    .s_axi_lite_arvalid(arvalid), .s_axi_lite_arready(arready), .s_axi_lite_araddr(araddr),
    .s_axi_lite_rvalid(rvalid_lite), .s_axi_lite_rready(rready_lite),
    .s_axi_lite_rdata(rdata_lite), .s_axi_lite_rresp(rresp_lite),
    .m_axi_mm2s_araddr(dma_araddr), .m_axi_mm2s_arlen(dma_arlen),
    .m_axi_mm2s_arsize(dma_arsize), .m_axi_mm2s_arburst(dma_arburst),
    .m_axi_mm2s_arprot(dma_arprot), .m_axi_mm2s_arcache(dma_arcache),
    .m_axi_mm2s_arvalid(dma_arvalid), .m_axi_mm2s_arready(dma_arready),
    .m_axi_mm2s_rdata(dma_rdata), .m_axi_mm2s_rresp(dma_rresp),
    .m_axi_mm2s_rlast(dma_rlast), .m_axi_mm2s_rvalid(dma_rvalid),
    .m_axi_mm2s_rready(dma_rready),
    .m_axis_mm2s_tdata(tdata), .m_axis_mm2s_tkeep(tkeep),
    .m_axis_mm2s_tvalid(tvalid), .m_axis_mm2s_tready(tready), .m_axis_mm2s_tlast(tlast),
    .m_axi_s2mm_awaddr(dma_awaddr), .m_axi_s2mm_awlen(dma_awlen),
    .m_axi_s2mm_awsize(dma_awsize), .m_axi_s2mm_awprot(dma_awprot),
    .m_axi_s2mm_awburst(dma_awburst), .m_axi_s2mm_awcache(dma_awcache),
    .m_axi_s2mm_awvalid(dma_awvalid), .m_axi_s2mm_awready(dma_awready),
    .m_axi_s2mm_wdata(dma_wdata), .m_axi_s2mm_wstrb(dma_wstrb),
    .m_axi_s2mm_wlast(dma_wlast), .m_axi_s2mm_wvalid(dma_wvalid), .m_axi_s2mm_wready(dma_wready),
    .m_axi_s2mm_bresp(dma_bresp), .m_axi_s2mm_bvalid(dma_bvalid), .m_axi_s2mm_bready(dma_bready),
    .s_axis_s2mm_tdata(axis_data), .s_axis_s2mm_tkeep(axis_keep),
    .s_axis_s2mm_tvalid(axis_valid), .s_axis_s2mm_tready(axis_ready), .s_axis_s2mm_tlast(axis_last)
  );

  vendor_dma_write_peer writer (
    .clk(clk), .resetn(resetn),
    .dma_awaddr(dma_awaddr), .dma_awlen(dma_awlen), .dma_awsize(dma_awsize),
    .dma_awprot(dma_awprot), .dma_awburst(dma_awburst), .dma_awcache(dma_awcache),
    .dma_awvalid(dma_awvalid), .dma_awready(dma_awready),
    .dma_wdata(dma_wdata), .dma_wstrb(dma_wstrb), .dma_wlast(dma_wlast),
    .dma_wvalid(dma_wvalid), .dma_wready(dma_wready),
    .dma_bresp(dma_bresp), .dma_bvalid(dma_bvalid), .dma_bready(dma_bready),
    .axis_data(axis_data), .axis_keep(axis_keep), .axis_valid(axis_valid),
    .axis_last(axis_last), .axis_ready(axis_ready)
  );

  filter_candidate_pf_memory_imp_auto_pc_0 converter (
    .aclk(clk), .aresetn(resetn),
    .s_axi_araddr(dma_araddr), .s_axi_arlen(dma_arlen), .s_axi_arsize(dma_arsize),
    .s_axi_arburst(dma_arburst), .s_axi_arlock(1'b0), .s_axi_arcache(dma_arcache),
    .s_axi_arprot(dma_arprot), .s_axi_arregion(4'b0), .s_axi_arqos(4'b0),
    .s_axi_arvalid(dma_arvalid), .s_axi_arready(dma_arready),
    .s_axi_rdata(dma_rdata), .s_axi_rresp(dma_rresp), .s_axi_rlast(dma_rlast),
    .s_axi_rvalid(dma_rvalid), .s_axi_rready(dma_rready),
    .m_axi_araddr(mem_araddr), .m_axi_arlen(mem_arlen), .m_axi_arsize(mem_arsize),
    .m_axi_arburst(mem_arburst), .m_axi_arlock(mem_arlock), .m_axi_arcache(mem_arcache),
    .m_axi_arprot(mem_arprot), .m_axi_arqos(mem_arqos),
    .m_axi_arvalid(mem_arvalid), .m_axi_arready(mem_arready),
    .m_axi_rdata(mem_rdata), .m_axi_rresp(mem_rresp), .m_axi_rlast(mem_rlast),
    .m_axi_rvalid(mem_rvalid), .m_axi_rready(mem_rready)
  );

  reg [31:0] mem_addr = 0;
  reg [3:0] mem_len = 0, mem_index = 0;
  integer ar_count = 0, stream_count = 0, post_reset_leaks = 0;
  integer discarded_drain_beats = 0;
  reg monitor_quiet = 0;
  reg enforce_quiet = 0;
  reg [31:0] expected_source = 0;
  function automatic [63:0] sample(input [31:0] addr);
    sample = 64'hcafe_0000_0000_0000 | {32'b0,addr};
  endfunction

  always @(posedge clk) begin
    if (!resetn && flush_memory_on_reset) begin
      mem_active <= 0;
      mem_rvalid <= 0;
      mem_index <= 0;
    end else begin
    if (mem_arvalid && mem_arready) begin
      if (mem_active) $fatal(1, "memory model received overlapping AR");
      mem_active <= 1;
      mem_addr <= mem_araddr;
      mem_len <= mem_arlen;
      mem_index <= 0;
      ar_count <= ar_count + 1;
      $display("AXI3_AR addr=%h len=%0d time=%0t", mem_araddr, mem_arlen, $time);
    end
    if (mem_active && !mem_stall && !mem_rvalid) begin
      mem_rvalid <= 1;
      mem_rdata <= sample(mem_addr + 8*mem_index);
      mem_rlast <= mem_index == mem_len;
    end
    if (mem_rvalid && mem_rready) begin
      $display("AXI3_R data=%h last=%b time=%0t",mem_rdata,mem_rlast,$time);
      mem_rvalid <= 0;
      if (mem_index == mem_len) mem_active <= 0;
      else mem_index <= mem_index + 1;
    end
    end
    if (tvalid && tready) begin
      if (monitor_quiet) begin
        discarded_drain_beats <= discarded_drain_beats + 1;
        $display("QUIET_STREAM time=%0t resetn=%b data=%h last=%b",$time,resetn,tdata,tlast);
        if (enforce_quiet) post_reset_leaks <= post_reset_leaks + 1;
      end
      else begin
        if (tdata !== sample(expected_source + stream_count*8))
          $fatal(1, "stream mismatch beat=%0d data=%h expected=%h", stream_count, tdata,
                 sample(expected_source + stream_count*8));
        if (tkeep !== 8'hff) $fatal(1, "bad keep");
        if (stream_count >= 8 || tlast !== (stream_count == 7)) $fatal(1,"bad TLAST/count");
        stream_count <= stream_count + 1;
        $display("STREAM beat=%0d data=%h last=%b", stream_count, tdata, tlast);
      end
    end
  end

  task automatic wr(input [9:0] addr, input [31:0] data);
    integer watchdog;
    reg aw_done, w_done;
    begin
      @(negedge clk);
      awaddr = addr; wdata = data; awvalid = 1; wvalid = 1;
      watchdog = 0;
      aw_done=0; w_done=0;
      while (!(aw_done && w_done)) begin
        @(posedge clk);
        if (awvalid && awready) aw_done=1;
        if (wvalid && wready) w_done=1;
        @(negedge clk);
        if (aw_done) awvalid=0;
        if (w_done) wvalid=0;
        watchdog = watchdog + 1;
        if (watchdog > 1000) $fatal(1, "AXI-Lite write timeout addr=%h", addr);
      end
      watchdog = 0;
      while (!bvalid) begin
        @(negedge clk); watchdog = watchdog + 1;
        if (watchdog > 1000) $fatal(1, "AXI-Lite B timeout addr=%h", addr);
      end
      if (bresp !== 0) $fatal(1, "AXI-Lite BRESP=%b", bresp);
      bready=1;
      @(posedge clk);
      @(negedge clk); bready=0;
    end
  endtask

  task automatic rd(input [9:0] addr, output reg [31:0] value);
    integer watchdog;
    begin
      @(negedge clk); araddr=addr; arvalid=1; rready_lite=0;
      watchdog=0;
      do begin
        @(posedge clk); watchdog=watchdog+1;
        if (watchdog>1000) $fatal(1,"AXI-Lite AR timeout");
      end while (!arready);
      @(negedge clk); arvalid=0;
      watchdog=0;
      while (!rvalid_lite) begin
        @(negedge clk); watchdog=watchdog+1;
        if (watchdog>1000) $fatal(1,"AXI-Lite R timeout");
      end
      if (rresp_lite !== 0) $fatal(1,"AXI-Lite RRESP error");
      value=rdata_lite; rready_lite=1;
      @(posedge clk);
      @(negedge clk); rready_lite=0;
    end
  endtask

  task automatic start_write(input [31:0] addr);
    begin
      wr(10'h030,32'h1); wr(10'h048,addr); wr(10'h058,32'd64);
    end
  endtask

  task automatic completed_status;
    reg [31:0] read_status, write_status;
    begin
      rd(10'h004,read_status); rd(10'h034,write_status);
      $display("DUPLEX_STATUS mm2s=%h s2mm=%h",read_status,write_status);
      if ((read_status & 32'h5772) !== 32'h1002 || (write_status & 32'h5772) !== 32'h1002)
        $fatal(1,"duplex status not IOC+idle/no-error");
      wr(10'h004,32'h1000); wr(10'h034,32'h1000);
    end
  endtask

  task automatic duplex_scenario;
    integer count, target_b;
    reg [31:0] read_cr, write_cr, read_sr, write_sr;
    reg soft_inflight, drain_first, never_release;
    begin
      soft_inflight=$test$plusargs("soft_reset_inflight");
      drain_first=$test$plusargs("drain_before_reset");
      never_release=$test$plusargs("never_release");
      writer.flush_on_reset=flush_memory_on_reset;
      start_write(32'h4000);
      fork
        writer.send(32'h1111);
        start_read(32'h1000);
      join
      count=0;
      while (stream_count<8 || writer.b_count<1) begin
        @(negedge clk); count=count+1;
        if(count>2000) $fatal(1,"normal duplex timeout");
      end
      writer.check_frame(0,32'h1111);
      completed_status();
      $display("NORMAL_DUPLEX_PASS");
      start_write(32'h5000);
      writer.stall_after_two=1;
      fork
        writer.send(32'h2222);
        begin
          start_read(32'h2000);
          wait(stream_count>=2);
          @(negedge clk); mem_stall=1;
        end
      join
      count=0;
      while(writer.w_count<10) begin
        @(negedge clk); count=count+1;
        if(count>2000) $fatal(1,"duplex inflight setup timeout");
      end
      writer.stall=1;
      if(mem_active !== 1 || writer.active !== 1 || writer.beat_index !== 2)
        $fatal(1,"both directions not simultaneously outstanding");
      $display("BOTH_INFLIGHT_CONFIRMED read_addr=%h read_index=%0d write_addr=%h write_index=%0d",mem_addr,mem_index,writer.active_addr,writer.beat_index);
      if(drain_first) begin
        mem_stall=0; writer.stall=0; writer.stall_after_two=0;
        count=0;
        while(stream_count<8 || writer.b_count<2) begin
          @(negedge clk); count=count+1;
          if(count>2000) $fatal(1,"duplex pre-reset drain timeout");
        end
        writer.check_frame(1,32'h2222);
        completed_status();
        if(mem_active || writer.active || writer.mem_bvalid) $fatal(1,"not drained");
        $display("BOTH_DRAINED_BEFORE_EXTERNAL_RESET");
      end
      monitor_quiet=1;
      if(soft_inflight) wr(10'h000,32'h4);
      else begin resetn=0; repeat(25) @(negedge clk); resetn=1; end
      enforce_quiet=!soft_inflight;
      if(!never_release) begin mem_stall=0; writer.stall=0; writer.stall_after_two=0; end
      repeat(100) @(negedge clk);
      if(post_reset_leaks != 0) $fatal(1,"old duplex stream leaked");
      $display("DUPLEX_POST_RESET outstanding_read=%b outstanding_write=%b writes=%0d",mem_active,writer.active,writer.w_count);
      if(soft_inflight) begin
        count=0;
        do begin
          rd(10'h000,read_cr); rd(10'h030,write_cr);
          rd(10'h004,read_sr); rd(10'h034,write_sr);
          count=count+1;
        end while (count<20 && (read_cr[2] || write_cr[2] || !read_sr[0] || !write_sr[0] || mem_active || writer.active || writer.mem_bvalid));
        if(never_release) begin
          if(!mem_active || !writer.active) $fatal(1,"blocked bursts unexpectedly cleared");
          if(read_cr[2] !== 1 || write_cr[2] !== 1 || read_sr[0] !== 0 || write_sr[0] !== 0)
            $fatal(1,"blocked reset/halt state unexpectedly completed");
          $display("BLOCKED_DRAIN_NO_RESTART_PASS read_cr=%h write_cr=%h read_sr=%h write_sr=%h",read_cr,write_cr,read_sr,write_sr);
          $finish;
        end
        if(read_cr[2] || write_cr[2] || !read_sr[0] || !write_sr[0] || mem_active || writer.active || writer.mem_bvalid)
          $fatal(1,"duplex software reset did not drain/halt");
        enforce_quiet=1;
        repeat(30) @(negedge clk);
        if(post_reset_leaks != 0) $fatal(1,"old duplex stream after confirmed halt");
        $display("SOFT_DUPLEX_DRAIN_AND_HALT_CONFIRMED old_write_buffer_discarded=1 discarded_stream_beats=%0d",discarded_drain_beats);
      end
      target_b=writer.b_count+1;
      if($test$plusargs("write_restart_first")) begin
        // Isolate write corruption before the stale read assertion stops the run.
        start_write(32'h6000);
        writer.send(32'h3333);
        count=0;
        while(writer.b_count<target_b) begin
          @(negedge clk); count=count+1;
          if(count>2000) $fatal(1,"write-first duplex restart timeout");
        end
        writer.check_frame(2,32'h3333);
        $fatal(1,"unsafe retained write unexpectedly completed");
      end
      monitor_quiet=0;
      start_write(32'h6000);
      fork writer.send(32'h3333); start_read(32'h3000); join
      count=0;
      while(stream_count<8 || writer.b_count<target_b) begin
        @(negedge clk); count=count+1;
        if(count>2000) $fatal(1,"post-reset duplex timeout");
      end
      writer.check_frame(2,32'h3333);
      completed_status();
      $display("POST_RESET_DUPLEX_PASS");
      $finish;
    end
  endtask

  task automatic start_read(input [31:0] addr);
    begin
      expected_source = addr;
      stream_count = 0;
      wr(10'h000,32'h1);
      wr(10'h018,addr);
      wr(10'h028,32'd64);
    end
  endtask

  initial begin : scenario
    integer count;
    reg soft_inflight;
    flush_memory_on_reset = $test$plusargs("flush_memory_on_reset");
    soft_inflight = $test$plusargs("soft_reset_inflight");
    $display("MEMORY_FLUSH_ON_RESET=%b",flush_memory_on_reset);
    $display("SOFT_RESET_INFLIGHT=%b",soft_inflight);
    repeat (25) @(negedge clk);
    resetn = 1;
    repeat (80) @(negedge clk);
    if($test$plusargs("duplex")) duplex_scenario();
    start_read(32'h1000);
    count = 0;
    while (stream_count < 8) begin
      @(negedge clk); count = count + 1;
      if (count > 2000) $fatal(1,"normal transfer timeout ar=%0d stream=%0d", ar_count, stream_count);
    end
    $display("NORMAL_READ_PASS");
    repeat (30) @(negedge clk);
    start_read(32'h2000);
    count = 0;
    while (stream_count < 2) begin
      @(negedge clk); count = count + 1;
      if (count > 2000) $fatal(1,"inflight setup timeout");
    end
    mem_stall = 1;
    monitor_quiet = 1;
    if (soft_inflight) begin
      wr(10'h000,32'h4);
      repeat (25) @(negedge clk);
    end else begin
      resetn = 0;
      repeat (25) @(negedge clk);
      resetn = 1;
    end
    enforce_quiet = 1;
    mem_stall = 0;
    repeat (100) @(negedge clk);
    if (post_reset_leaks != 0) $fatal(1,"old stream leaked after reset: %0d",post_reset_leaks);
    $display("READ_RESET_QUIET_PASS outstanding=%b",mem_active);
    if ($test$plusargs("software_quiesce")) begin
      $display("SOFTWARE_QUIESCE_BEFORE_RESTART");
      wr(10'h000,32'h4);
      repeat (80) @(negedge clk);
    end
    monitor_quiet = 0;
    start_read(32'h3000);
    count = 0;
    while (stream_count < 8) begin
      @(negedge clk); count = count + 1;
      if (count > 2000) $fatal(1,"post-reset read stuck: memory_outstanding=%b ar=%0d beats=%0d",mem_active,ar_count,stream_count);
    end
    $display("POST_RESET_READ_PASS");
    $finish;
  end

  initial begin
    #200000;
    $fatal(1,"global watchdog");
  end
endmodule
