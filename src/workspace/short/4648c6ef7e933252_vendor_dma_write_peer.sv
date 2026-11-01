`timescale 1ns/1ps

// S2MM peer for the same DMA instance used by the MM2S testbench.
module vendor_dma_write_peer (
  input wire clk, resetn,
  input wire [31:0] dma_awaddr,
  input wire [7:0] dma_awlen,
  input wire [2:0] dma_awsize, dma_awprot,
  input wire [1:0] dma_awburst,
  input wire [3:0] dma_awcache,
  input wire dma_awvalid, output wire dma_awready,
  input wire [63:0] dma_wdata, input wire [7:0] dma_wstrb,
  input wire dma_wlast, dma_wvalid, output wire dma_wready,
  output wire [1:0] dma_bresp, output wire dma_bvalid, input wire dma_bready,
  output reg [63:0] axis_data = 0,
  output wire [7:0] axis_keep,
  output reg axis_valid = 0, axis_last = 0, input wire axis_ready
);
  assign axis_keep = 8'hff;
  wire [31:0] mem_awaddr;
  wire [3:0] mem_awlen;
  wire mem_awvalid, mem_awready;
  wire [63:0] mem_wdata;
  wire [7:0] mem_wstrb;
  wire mem_wlast, mem_wvalid, mem_wready, mem_bready;
  reg mem_bvalid = 0;
  reg active = 0, stall = 0, stall_after_two = 0, flush_on_reset = 0;
  reg [31:0] active_addr = 0;
  reg [3:0] active_len = 0, beat_index = 0;
  integer aw_count = 0, w_count = 0, b_count = 0;
  reg [63:0] dst0 [0:7], dst1 [0:7], dst2 [0:7];
  assign mem_awready = !active && !mem_bvalid;
  assign mem_wready = active && !stall && !(stall_after_two && w_count >= 10);

  filter_candidate_pf_memory_imp_auto_pc_1 converter (
    .aclk(clk), .aresetn(resetn),
    .s_axi_awaddr(dma_awaddr), .s_axi_awlen(dma_awlen), .s_axi_awsize(dma_awsize),
    .s_axi_awburst(dma_awburst), .s_axi_awlock(1'b0), .s_axi_awcache(dma_awcache),
    .s_axi_awprot(dma_awprot), .s_axi_awregion(4'b0), .s_axi_awqos(4'b0),
    .s_axi_awvalid(dma_awvalid), .s_axi_awready(dma_awready),
    .s_axi_wdata(dma_wdata), .s_axi_wstrb(dma_wstrb), .s_axi_wlast(dma_wlast),
    .s_axi_wvalid(dma_wvalid), .s_axi_wready(dma_wready),
    .s_axi_bresp(dma_bresp), .s_axi_bvalid(dma_bvalid), .s_axi_bready(dma_bready),
    .m_axi_awaddr(mem_awaddr), .m_axi_awlen(mem_awlen),
    .m_axi_awvalid(mem_awvalid), .m_axi_awready(mem_awready),
    .m_axi_wdata(mem_wdata), .m_axi_wstrb(mem_wstrb), .m_axi_wlast(mem_wlast),
    .m_axi_wvalid(mem_wvalid), .m_axi_wready(mem_wready),
    .m_axi_bresp(2'b00), .m_axi_bvalid(mem_bvalid), .m_axi_bready(mem_bready)
  );

  always @(posedge clk) begin
    if (!resetn && flush_on_reset) begin
      active <= 0;
      mem_bvalid <= 0;
      beat_index <= 0;
    end else begin
      if (mem_awvalid && mem_awready) begin
        if (mem_awlen !== 7) $fatal(1,"unexpected write burst length %d",mem_awlen);
        active <= 1;
        active_addr <= mem_awaddr;
        active_len <= mem_awlen;
        beat_index <= 0;
        aw_count <= aw_count + 1;
        $display("DUPLEX_AXI3_AW addr=%h len=%0d time=%0t",mem_awaddr,mem_awlen,$time);
      end
      if (mem_wvalid && mem_wready) begin
        if (mem_wstrb !== 8'hff || mem_wlast !== (beat_index == active_len))
          $fatal(1,"duplex bad WSTRB/WLAST at %0d",beat_index);
        case (active_addr)
          32'h4000: dst0[beat_index] <= mem_wdata;
          32'h5000: dst1[beat_index] <= mem_wdata;
          32'h6000: dst2[beat_index] <= mem_wdata;
          default: $fatal(1,"unexpected duplex AW address %h",active_addr);
        endcase
        $display("DUPLEX_AXI3_W addr=%h index=%0d data=%h time=%0t",active_addr,beat_index,mem_wdata,$time);
        w_count <= w_count + 1;
        if (beat_index == active_len) begin
          active <= 0;
          mem_bvalid <= 1;
        end else beat_index <= beat_index + 1;
      end
      if (mem_bvalid && mem_bready) begin
        mem_bvalid <= 0;
        b_count <= b_count + 1;
        $display("DUPLEX_AXI3_B accepted time=%0t",$time);
      end
    end
  end

  task automatic send(input [31:0] marker);
    integer n, watchdog;
    begin
      for (n=0; n<8; n=n+1) begin
        @(negedge clk);
        axis_data = {marker,n[31:0]}; axis_last = n==7; axis_valid = 1;
        watchdog = 0;
        do begin
          @(posedge clk); watchdog = watchdog + 1;
          if (watchdog > 2000) $fatal(1,"duplex AXIS input timeout beat=%0d",n);
        end while (!axis_ready);
        @(negedge clk); axis_valid = 0;
      end
    end
  endtask

  task automatic check_frame(input integer frame, input [31:0] marker);
    integer n;
    reg [63:0] value;
    begin
      for (n=0; n<8; n=n+1) begin
        case(frame)
          0: value = dst0[n];
          1: value = dst1[n];
          2: value = dst2[n];
          default: $fatal(1,"bad frame index");
        endcase
        if (value !== {marker,n[31:0]})
          $fatal(1,"duplex write mismatch frame=%0d beat=%0d data=%h",frame,n,value);
      end
    end
  endtask

  integer i;
  initial for(i=0;i<8;i=i+1) begin dst0[i]=0; dst1[i]=0; dst2[i]=0; end
endmodule
