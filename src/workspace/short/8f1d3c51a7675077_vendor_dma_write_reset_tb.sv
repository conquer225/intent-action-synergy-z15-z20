`timescale 1ns/1ps

// Vendor AXI DMA + generated AXI4-to-AXI3 write converter. The downstream
// AXI3 memory agent intentionally keeps an accepted burst across PL reset.
module vendor_dma_write_reset_tb;
  reg clk = 0;
  always #10 clk = ~clk;
  reg resetn = 0;
  reg lite_awvalid = 0, lite_wvalid = 0, lite_bready = 1, lite_arvalid = 0, lite_rready = 1;
  reg [9:0] lite_awaddr = 0;
  reg [9:0] lite_araddr = 0;
  reg [31:0] lite_wdata = 0;
  wire lite_awready, lite_wready, lite_bvalid;
  wire lite_arready, lite_rvalid;
  wire [31:0] lite_rdata;
  wire [1:0] lite_bresp;
  wire [31:0] dma_awaddr;
  wire [7:0] dma_awlen;
  wire [2:0] dma_awsize, dma_awprot;
  wire [1:0] dma_awburst;
  wire [3:0] dma_awcache;
  wire dma_awvalid, dma_awready;
  wire [63:0] dma_wdata;
  wire [7:0] dma_wstrb;
  wire dma_wlast, dma_wvalid, dma_wready;
  wire [1:0] dma_bresp;
  wire dma_bvalid, dma_bready;
  wire [31:0] mem_awaddr;
  wire [3:0] mem_awlen;
  wire [1:0] mem_awlock, mem_awburst;
  wire [2:0] mem_awsize, mem_awprot;
  wire [3:0] mem_awcache, mem_awqos;
  wire mem_awvalid, mem_awready;
  wire [63:0] mem_wdata;
  wire [7:0] mem_wstrb;
  wire mem_wlast, mem_wvalid, mem_wready, mem_bready;
  reg mem_bvalid = 0;
  reg [1:0] mem_bresp = 0;
  reg [63:0] axis_data = 0;
  reg [7:0] axis_keep = 8'hff;
  reg axis_valid = 0, axis_last = 0;
  wire axis_ready;

  filter_candidate_pf_dma_0 dma (
    .s_axi_lite_aclk(clk), .m_axi_mm2s_aclk(clk), .m_axi_s2mm_aclk(clk), .axi_resetn(resetn),
    .s_axi_lite_awvalid(lite_awvalid), .s_axi_lite_awready(lite_awready), .s_axi_lite_awaddr(lite_awaddr),
    .s_axi_lite_wvalid(lite_wvalid), .s_axi_lite_wready(lite_wready), .s_axi_lite_wdata(lite_wdata),
    .s_axi_lite_bresp(lite_bresp), .s_axi_lite_bvalid(lite_bvalid), .s_axi_lite_bready(lite_bready),
    .s_axi_lite_arvalid(lite_arvalid), .s_axi_lite_arready(lite_arready),
    .s_axi_lite_araddr(lite_araddr), .s_axi_lite_rready(lite_rready),
    .s_axi_lite_rvalid(lite_rvalid), .s_axi_lite_rdata(lite_rdata),
    .m_axi_mm2s_arready(1'b0), .m_axi_mm2s_rdata(64'b0), .m_axi_mm2s_rresp(2'b00),
    .m_axi_mm2s_rlast(1'b0), .m_axi_mm2s_rvalid(1'b0), .m_axis_mm2s_tready(1'b1),
    .m_axi_s2mm_awaddr(dma_awaddr), .m_axi_s2mm_awlen(dma_awlen),
    .m_axi_s2mm_awsize(dma_awsize), .m_axi_s2mm_awburst(dma_awburst),
    .m_axi_s2mm_awprot(dma_awprot), .m_axi_s2mm_awcache(dma_awcache),
    .m_axi_s2mm_awvalid(dma_awvalid), .m_axi_s2mm_awready(dma_awready),
    .m_axi_s2mm_wdata(dma_wdata), .m_axi_s2mm_wstrb(dma_wstrb),
    .m_axi_s2mm_wlast(dma_wlast), .m_axi_s2mm_wvalid(dma_wvalid), .m_axi_s2mm_wready(dma_wready),
    .m_axi_s2mm_bresp(dma_bresp), .m_axi_s2mm_bvalid(dma_bvalid), .m_axi_s2mm_bready(dma_bready),
    .s_axis_s2mm_tdata(axis_data), .s_axis_s2mm_tkeep(axis_keep),
    .s_axis_s2mm_tvalid(axis_valid), .s_axis_s2mm_tready(axis_ready), .s_axis_s2mm_tlast(axis_last)
  );

  filter_candidate_pf_memory_imp_auto_pc_1 converter (
    .aclk(clk), .aresetn(resetn),
    .s_axi_awaddr(dma_awaddr), .s_axi_awlen(dma_awlen), .s_axi_awsize(dma_awsize),
    .s_axi_awburst(dma_awburst), .s_axi_awlock(1'b0), .s_axi_awcache(dma_awcache),
    .s_axi_awprot(dma_awprot), .s_axi_awregion(4'b0), .s_axi_awqos(4'b0),
    .s_axi_awvalid(dma_awvalid), .s_axi_awready(dma_awready),
    .s_axi_wdata(dma_wdata), .s_axi_wstrb(dma_wstrb), .s_axi_wlast(dma_wlast),
    .s_axi_wvalid(dma_wvalid), .s_axi_wready(dma_wready),
    .s_axi_bresp(dma_bresp), .s_axi_bvalid(dma_bvalid), .s_axi_bready(dma_bready),
    .m_axi_awaddr(mem_awaddr), .m_axi_awlen(mem_awlen), .m_axi_awsize(mem_awsize),
    .m_axi_awburst(mem_awburst), .m_axi_awlock(mem_awlock), .m_axi_awcache(mem_awcache),
    .m_axi_awprot(mem_awprot), .m_axi_awqos(mem_awqos),
    .m_axi_awvalid(mem_awvalid), .m_axi_awready(mem_awready),
    .m_axi_wdata(mem_wdata), .m_axi_wstrb(mem_wstrb), .m_axi_wlast(mem_wlast),
    .m_axi_wvalid(mem_wvalid), .m_axi_wready(mem_wready),
    .m_axi_bresp(mem_bresp), .m_axi_bvalid(mem_bvalid), .m_axi_bready(mem_bready)
  );

  reg active = 0, stall = 0, stall_after_two = 0;
  reg flush_on_reset = 0;
  reg [31:0] active_addr = 0;
  reg [3:0] active_len = 0, beat_index = 0;
  integer aw_count = 0, w_count = 0;
  assign mem_awready = !active && !mem_bvalid;
  assign mem_wready = active && !stall && !(stall_after_two && w_count>=10);
  reg [63:0] dst0 [0:7];
  reg [63:0] dst1 [0:7];
  reg [63:0] dst2 [0:7];
  integer i;

  always @(posedge clk) begin
    if (!resetn && flush_on_reset) begin
      active <= 0;
      mem_bvalid <= 0;
      beat_index <= 0;
    end else begin
      if (mem_awvalid && mem_awready) begin
        active <= 1;
        active_addr <= mem_awaddr;
        active_len <= mem_awlen;
        beat_index <= 0;
        aw_count <= aw_count + 1;
        $display("AXI3_AW addr=%h len=%0d time=%0t",mem_awaddr,mem_awlen,$time);
      end
      if (mem_wvalid && mem_wready) begin
        if (mem_wstrb !== 8'hff || mem_wlast !== (beat_index == active_len))
          $fatal(1,"bad WSTRB/WLAST at %0d",beat_index);
        case (active_addr)
          32'h4000: dst0[beat_index] <= mem_wdata;
          32'h5000: dst1[beat_index] <= mem_wdata;
          32'h6000: dst2[beat_index] <= mem_wdata;
          default: $fatal(1,"unexpected AW address %h",active_addr);
        endcase
        $display("AXI3_W addr=%h index=%0d data=%h time=%0t",active_addr,beat_index,mem_wdata,$time);
        w_count <= w_count + 1;
        if (beat_index == active_len) begin
          active <= 0;
          mem_bvalid <= 1;
        end else beat_index <= beat_index + 1;
      end
      if (mem_bvalid && mem_bready) begin
        $display("AXI3_B accepted time=%0t",$time);
        mem_bvalid <= 0;
      end
    end
  end

  task automatic wr(input [9:0] addr, input [31:0] data);
    integer watchdog;
    begin
      @(negedge clk);
      lite_awaddr = addr; lite_wdata = data; lite_awvalid = 1; lite_wvalid = 1;
      watchdog = 0;
      while (!(lite_awready && lite_wready)) begin
        @(negedge clk); watchdog = watchdog + 1;
        if (watchdog > 1000) $fatal(1,"AXI-Lite write timeout addr=%h",addr);
      end
      @(negedge clk); lite_awvalid = 0; lite_wvalid = 0;
      watchdog = 0;
      while (!lite_bvalid) begin
        @(negedge clk); watchdog = watchdog + 1;
        if (watchdog > 1000) $fatal(1,"AXI-Lite B timeout addr=%h",addr);
      end
      if (lite_bresp !== 0) $fatal(1,"AXI-Lite B error");
    end
  endtask

  task automatic send(input integer count, input [31:0] marker);
    integer n, watchdog;
    begin
      for (n=0; n<count; n=n+1) begin
        @(negedge clk);
        axis_data = {marker,n[31:0]};
        axis_last = n==7;
        axis_valid = 1;
        watchdog = 0;
        while (!axis_ready) begin
          @(negedge clk); watchdog = watchdog + 1;
          if (watchdog > 2000) $fatal(1,"AXIS input timeout beat=%0d",n);
        end
        @(negedge clk); axis_valid = 0;
      end
    end
  endtask

  task automatic rd(input [9:0] addr, output reg [31:0] value);
    integer watchdog;
    begin
      @(negedge clk); lite_araddr=addr; lite_arvalid=1;
      watchdog=0;
      while (!lite_arready) begin
        @(negedge clk); watchdog=watchdog+1;
        if (watchdog>1000) $fatal(1,"AXI-Lite AR timeout");
      end
      @(negedge clk); lite_arvalid=0;
      watchdog=0;
      while (!lite_rvalid) begin
        @(negedge clk); watchdog=watchdog+1;
        if (watchdog>1000) $fatal(1,"AXI-Lite R timeout");
      end
      value=lite_rdata;
    end
  endtask

  task automatic start_write(input [31:0] addr);
    begin
      wr(10'h030,32'h1);
      wr(10'h048,addr);
      wr(10'h058,32'd64);
    end
  endtask

  initial begin : scenario
    integer watchdog, target_w_count;
    reg [31:0] status;
    reg soft_inflight;
    flush_on_reset = $test$plusargs("flush_memory_on_reset");
    soft_inflight = $test$plusargs("soft_reset_inflight");
    for (i=0;i<8;i=i+1) begin dst0[i]=0; dst1[i]=0; dst2[i]=0; end
    $display("MEMORY_FLUSH_ON_RESET=%b",flush_on_reset);
    repeat (25) @(negedge clk);
    resetn = 1;
    repeat (80) @(negedge clk);
    start_write(32'h4000);
    send(8,32'h1111);
    watchdog=0;
    while (w_count<8) begin
      @(negedge clk); watchdog=watchdog+1;
      if (watchdog>2000) $fatal(1,"normal S2MM timeout aw=%0d w=%0d",aw_count,w_count);
    end
    for (i=0;i<8;i=i+1)
      if (dst0[i] !== {32'h1111,i[31:0]}) $fatal(1,"normal write mismatch beat=%0d data=%h",i,dst0[i]);
    $display("NORMAL_WRITE_PASS");
    $display("NORMAL_POST active=%b bvalid=%b bready=%b dma_awvalid=%b dma_awready=%b",active,mem_bvalid,mem_bready,dma_awvalid,dma_awready);
    repeat (30) @(negedge clk);
    rd(10'h034,status);
    $display("S2MM_STATUS_AFTER_NORMAL=%h",status);
    start_write(32'h5000);
    stall_after_two = 1;
    send(8,32'h2222);
    watchdog=0;
    while (w_count<10) begin
      @(negedge clk); watchdog=watchdog+1;
      if (watchdog>2000) $fatal(1,"partial S2MM setup timeout aw=%0d w=%0d",aw_count,w_count);
    end
    stall = 1;
    if (soft_inflight) begin
      wr(10'h000,32'h4);
      repeat (25) @(negedge clk);
    end else begin
      resetn = 0;
      repeat (25) @(negedge clk);
      resetn = 1;
    end
    stall = 0;
    stall_after_two = 0;
    repeat (100) @(negedge clk);
    $display("PARTIAL_WRITE_RETAINED outstanding=%b w=%0d dst1[0]=%h dst1[1]=%h",active,w_count,dst1[0],dst1[1]);
    target_w_count = w_count + 8;
    start_write(32'h6000);
    send(8,32'h3333);
    watchdog=0;
    while (w_count<target_w_count) begin
      @(negedge clk); watchdog=watchdog+1;
      if (watchdog>2000) $fatal(1,"postreset S2MM timeout aw=%0d w=%0d outstanding=%b",aw_count,w_count,active);
    end
    for (i=0;i<8;i=i+1)
      if (dst2[i] !== {32'h3333,i[31:0]}) $fatal(1,"postreset write mismatch beat=%0d data=%h",i,dst2[i]);
    $display("POST_RESET_WRITE_PASS");
    $finish;
  end
  initial begin
    #300000;
    $fatal(1,"global watchdog");
  end
endmodule
