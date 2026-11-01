`timescale 1ns/1ps
// No filter, DMA, crossbar or PL reset: drive the generated PS7 HP0 directly.
module hp0_ddr_probe_tb;
  reg ps_clk=0, por_n=1, sys_n=1;
  always #15 ps_clk=~ps_clk;
  wire ps_clk_pin=ps_clk, por_pin=por_n, sys_pin=sys_n;
  wire clk;
  reg awvalid=0,wvalid=0,wlast=0,bready=0,arvalid=0,rready=0;
  reg [31:0] awaddr=0,araddr=0;
  reg [63:0] wdata=0;
  wire awready,wready,bvalid,arready,rvalid,rlast;
  wire [1:0] bresp,rresp;
  wire [5:0] bid,rid;
  wire [63:0] rdata;
  localparam [31:0] BASE=32'h00200000;
  localparam [63:0] SENTINEL=64'hdeadbeefdeadbeef;
  filter_candidate_processing_system7_0_0 ps (
    .PS_CLK(ps_clk_pin),.PS_PORB(por_pin),.PS_SRSTB(sys_pin),.FCLK_CLK0(clk),
    .M_AXI_GP0_ACLK(clk),.M_AXI_GP0_ARREADY(1'b0),.M_AXI_GP0_AWREADY(1'b0),
    .M_AXI_GP0_WREADY(1'b0),.M_AXI_GP0_BVALID(1'b0),.M_AXI_GP0_BID(12'b0),
    .M_AXI_GP0_BRESP(2'b0),.M_AXI_GP0_RVALID(1'b0),.M_AXI_GP0_RLAST(1'b0),
    .M_AXI_GP0_RID(12'b0),.M_AXI_GP0_RRESP(2'b0),.M_AXI_GP0_RDATA(32'b0),
    .S_AXI_HP0_ACLK(clk),.S_AXI_HP0_AWID(6'd2),.S_AXI_HP0_AWADDR(awaddr),
    .S_AXI_HP0_AWLEN(4'd15),.S_AXI_HP0_AWSIZE(3'd3),.S_AXI_HP0_AWBURST(2'b01),
    .S_AXI_HP0_AWLOCK(2'b0),.S_AXI_HP0_AWCACHE(4'b0011),.S_AXI_HP0_AWPROT(3'b0),
    .S_AXI_HP0_AWQOS(4'b0),.S_AXI_HP0_AWVALID(awvalid),.S_AXI_HP0_AWREADY(awready),
    .S_AXI_HP0_WID(6'd2),.S_AXI_HP0_WDATA(wdata),.S_AXI_HP0_WSTRB(8'hff),
    .S_AXI_HP0_WLAST(wlast),.S_AXI_HP0_WVALID(wvalid),.S_AXI_HP0_WREADY(wready),
    .S_AXI_HP0_BID(bid),.S_AXI_HP0_BRESP(bresp),.S_AXI_HP0_BVALID(bvalid),.S_AXI_HP0_BREADY(bready),
    .S_AXI_HP0_ARID(6'd1),.S_AXI_HP0_ARADDR(araddr),.S_AXI_HP0_ARLEN(4'd15),
    .S_AXI_HP0_ARSIZE(3'd3),.S_AXI_HP0_ARBURST(2'b01),.S_AXI_HP0_ARLOCK(2'b0),
    .S_AXI_HP0_ARCACHE(4'b0011),.S_AXI_HP0_ARPROT(3'b0),.S_AXI_HP0_ARQOS(4'b0),
    .S_AXI_HP0_ARVALID(arvalid),.S_AXI_HP0_ARREADY(arready),
    .S_AXI_HP0_RID(rid),.S_AXI_HP0_RDATA(rdata),.S_AXI_HP0_RRESP(rresp),
    .S_AXI_HP0_RLAST(rlast),.S_AXI_HP0_RVALID(rvalid),.S_AXI_HP0_RREADY(rready),
    .S_AXI_HP0_RDISSUECAP1_EN(1'b0),.S_AXI_HP0_WRISSUECAP1_EN(1'b0)
  );
  integer aw_count=0,w_count=0,b_count=0,r_count=0;
  integer ddr_mismatches=0,frontdoor_mismatches=0;
  function automatic [63:0] word(input integer n);
    word={32'haced0050,n[31:0]};
  endfunction
  always @(posedge clk) begin
    if(awvalid && awready) begin
      if(awaddr !== BASE+aw_count*128) $fatal(1,"probe AW mismatch");
      aw_count<=aw_count+1;
    end
    if(wvalid && wready) begin
      if(wdata !== word(w_count) || wlast !== (w_count%16==15)) $fatal(1,"probe W mismatch");
      w_count<=w_count+1;
    end
    if(bvalid && bready) begin
      if(bresp !== 0 || bid !== 2) $fatal(1,"probe B error");
      b_count<=b_count+1;
    end
    if(rvalid && rready) begin
      if(rresp !== 0 || rid !== 1 || rlast !== (r_count%16==15)) $fatal(1,"probe R protocol error");
      if(rdata !== word(r_count)) frontdoor_mismatches<=frontdoor_mismatches+1;
      r_count<=r_count+1;
    end
  end
  always @(posedge ps.inst.net_sw_clk) begin
    if(ps.inst.ddrc.wr_req)
      $display("PROBE_DDR_CONSUME_EDGE addr=%h first=%h bytes=%0d",ps.inst.ddrc.wr_addr,ps.inst.ddrc.wr_data[63:0],ps.inst.ddrc.wr_bytes);
  end
  always @(negedge ps.inst.net_sw_clk) begin
    if(ps.inst.ddrc.wr_ack)
      $display("PROBE_DDR_AFTER_DELTA addr=%h first=%h",ps.inst.ddrc.wr_addr,ps.inst.ddrc.wr_data[63:0]);
  end
  task automatic write_burst(input integer n);
    integer i,timeout;
    begin
      @(negedge clk); awaddr=BASE+n*128; awvalid=1;
      timeout=0;
      do begin @(posedge clk); timeout=timeout+1; if(timeout>2000) $fatal(1,"probe AW timeout"); end while(!awready);
      @(negedge clk); awvalid=0;
      for(i=0;i<16;i=i+1) begin
        wdata=word(n*16+i); wlast=(i==15); wvalid=1; timeout=0;
        do begin @(posedge clk); timeout=timeout+1; if(timeout>2000) $fatal(1,"probe W timeout"); end while(!wready);
        @(negedge clk);
      end
      wvalid=0; wlast=0; bready=1; timeout=0;
      do begin @(posedge clk); timeout=timeout+1; if(timeout>2000) $fatal(1,"probe B timeout"); end while(!bvalid);
      @(negedge clk); bready=0;
      repeat(100) @(negedge clk);
    end
  endtask
  task automatic read_burst(input integer n);
    integer i,timeout;
    begin
      @(negedge clk); araddr=BASE+n*128; arvalid=1; timeout=0;
      do begin @(posedge clk); timeout=timeout+1; if(timeout>2000) $fatal(1,"probe AR timeout"); end while(!arready);
      @(negedge clk); arvalid=0; rready=1;
      for(i=0;i<16;i=i+1) begin
        timeout=0;
        do begin @(posedge clk); timeout=timeout+1; if(timeout>2000) $fatal(1,"probe R timeout"); end while(!rvalid);
        @(negedge clk);
      end
      rready=0;
    end
  endtask
  initial begin
    integer n;
    reg [1023:0] payload;
    #1; por_n=0; sys_n=0;
    repeat(25) @(negedge ps_clk); por_n=1; sys_n=1;
    repeat(60) @(negedge clk);
    ps.inst.set_debug_level_info(0);
    ps.inst.S_AXI_HP0.set_latency_type(0);
    for(n=0;n<80;n=n+1) begin
      payload=0; payload[63:0]=SENTINEL;
      ps.inst.write_mem(payload,BASE+n*8,8);
    end
    for(n=0;n<5;n=n+1) write_burst(n);
    repeat(1000) @(negedge clk);
    if(aw_count!=5 || w_count!=80 || b_count!=5) $fatal(1,"probe handshake counts wrong");
    $display("PROBE_HP_WRITES_PASS AW=5 W=80 B=5");
    for(n=0;n<80;n=n+1) begin
      ps.inst.read_mem(BASE+n*8,8,payload);
      if(payload[63:0] !== word(n)) begin
        ddr_mismatches=ddr_mismatches+1;
        $display("PROBE_BACKDOOR_MISMATCH word=%0d actual=%h expected=%h",n,payload[63:0],word(n));
      end
    end
    for(n=0;n<5;n=n+1) read_burst(n);
    if(r_count!=80) $fatal(1,"probe read count wrong");
    $display("PROBE_RESULT backdoor_mismatches=%0d frontdoor_mismatches=%0d",ddr_mismatches,frontdoor_mismatches);
    if(ddr_mismatches || frontdoor_mismatches) $fatal(1,"HP0_DDR_MINIMAL_REPRODUCED");
    $display("HP0_DDR_MINIMAL_PASS"); $finish;
  end
  initial begin #1000000; $fatal(1,"probe global watchdog"); end
endmodule
