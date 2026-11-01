`timescale 1ns/1ps

// Official PS7 VIP reset generator and the same AFI slave module used by HP0.
// The DDR backend supplies data only when requested by this test; not a DDRC model.
module vendor_hp0_reset_tb;
  reg clk=0;
  always #10 clk=~clk;
  reg por_n=1, sys_n=1;
  wire hp_resetn, fclk_resetn;
  processing_system7_vip_v1_0_24_gen_reset resetgen (
    .por_rst_n(por_n), .sys_rst_n(sys_n),
    .m_axi_gp0_clk(clk), .m_axi_gp1_clk(clk), .s_axi_gp0_clk(clk), .s_axi_gp1_clk(clk),
    .s_axi_hp0_clk(clk), .s_axi_hp1_clk(clk), .s_axi_hp2_clk(clk), .s_axi_hp3_clk(clk),
    .s_axi_acp_clk(clk), .s_axi_hp0_rstn(hp_resetn), .fclk_reset0_n(fclk_resetn)
  );
  reg arvalid=0, awvalid=0, wvalid=0, wlast=0, rready=0, bready=0;
  reg [63:0] wdata=0;
  wire arready, awready, wready, rvalid, rlast, bvalid;
  wire [63:0] rdata;
  wire [1:0] rresp, bresp;
  wire [5:0] rid, bid;
  wire rd_req, wr_valid;
  wire [31:0] rd_addr, wr_addr;
  wire [1023:0] wr_data;
  wire [8:0] rd_bytes, wr_bytes;
  wire [127:0] wr_strb;
  reg [1023:0] rd_data=0;
  reg rd_valid=0, wr_ack=0, reset_monitor=0;
  reg previous_req=0;
  integer ar_count=0, aw_count=0, w_count=0, r_count=0, b_count=0, req_count=0, backend_writes=0;

  // AFI resolves this function in its parent PS7 instance. This bench exercises
  // only DDR addresses; the range/type are from the vendor local_params/APIs.
  function automatic [1:0] decode_address(input [31:0] address);
    if(address >= 32'h00080000 && address <= 32'h7fffffff) decode_address=2'b01;
    else decode_address=2'b11;
  endfunction

  processing_system7_vip_v1_0_24_afi_slave #(
    .enable_this_port(1), .slave_name("HP0_RESET_AUDIT"), .data_bus_width(64),
    .address_bus_width(32), .id_bus_width(6),
    .slave_base_address(32'h00000000), .slave_high_address(32'hffffffff),
    .max_outstanding_transactions(16)
  ) hp0 (
    .S_RESETN(hp_resetn), .S_ACLK(clk), .SW_CLK(clk),
    .S_ARID(6'd1), .S_ARADDR(32'h00101000), .S_ARLEN(4'd7), .S_ARSIZE(3'd3),
    .S_ARBURST(2'b01), .S_ARLOCK(2'b00), .S_ARCACHE(4'b0011), .S_ARPROT(3'b000), .S_ARQOS(4'b0),
    .S_ARVALID(arvalid), .S_ARREADY(arready),
    .S_RID(rid), .S_RDATA(rdata), .S_RRESP(rresp), .S_RLAST(rlast), .S_RVALID(rvalid), .S_RREADY(rready),
    .S_AWID(6'd2), .S_AWADDR(32'h00102000), .S_AWLEN(4'd7), .S_AWSIZE(3'd3),
    .S_AWBURST(2'b01), .S_AWLOCK(2'b00), .S_AWCACHE(4'b0011), .S_AWPROT(3'b000), .S_AWQOS(4'b0),
    .S_AWVALID(awvalid), .S_AWREADY(awready),
    .S_WID(6'd2), .S_WDATA(wdata), .S_WSTRB(8'hff), .S_WLAST(wlast), .S_WVALID(wvalid), .S_WREADY(wready),
    .S_BID(bid), .S_BRESP(bresp), .S_BVALID(bvalid), .S_BREADY(bready),
    .S_RDISSUECAP1_EN(1'b0), .S_WRISSUECAP1_EN(1'b0),
    .WR_DATA_ACK_DDR(wr_ack), .WR_DATA_ACK_OCM(1'b0),
    .WR_DATA(wr_data), .WR_DATA_STRB(wr_strb), .WR_ADDR(wr_addr), .WR_BYTES(wr_bytes),
    .WR_DATA_VALID_DDR(wr_valid),
    .RD_REQ_DDR(rd_req), .RD_ADDR(rd_addr), .RD_BYTES(rd_bytes),
    .RD_DATA_DDR(rd_data), .RD_DATA_OCM(1024'b0),
    .RD_DATA_VALID_DDR(rd_valid), .RD_DATA_VALID_OCM(1'b0)
  );

  function automatic [63:0] read_word(input integer n);
    read_word={32'hcafe1111,n[31:0]};
  endfunction
  function automatic [63:0] write_word(input integer n);
    write_word={32'hbeef2222,n[31:0]};
  endfunction
  integer j;
  always @(posedge clk) begin
    if(reset_monitor && (hp_resetn !== 1 || rvalid !== 1 || rdata !== read_word(0) || rid !== 1))
      $fatal(1,"FCLK reset changed pending HP0 read/reset state");
    if(arvalid && arready) ar_count<=ar_count+1;
    if(awvalid && awready) aw_count<=aw_count+1;
    if(wvalid && wready) w_count<=w_count+1;
    if(rd_req) begin
      if(rd_addr !== 32'h00101000 || rd_bytes !== 64) $fatal(1,"HP0 backend read request mismatch");
      if(!previous_req) req_count<=req_count+1;
    end
    previous_req<=rd_req;
    if(rvalid && rready) begin
      if(r_count>=8 || rdata !== read_word(r_count) || rid !== 1 || rresp !== 0 || rlast !== (r_count==7))
        $fatal(1,"HP0 retained read mismatch beat=%0d data=%h",r_count,rdata);
      r_count<=r_count+1;
    end
    if(bvalid && bready) begin
      if(bid !== 2 || bresp !== 0) $fatal(1,"HP0 retained write response mismatch");
      b_count<=b_count+1;
    end
    wr_ack<=wr_valid;
    if(wr_valid && !wr_ack) begin
      if(wr_addr !== 32'h00102000 || wr_bytes !== 64 || wr_strb[63:0] !== 64'hffffffffffffffff)
        $fatal(1,"HP0 backend write address/size/strobe mismatch");
      for(j=0;j<8;j=j+1)
        if(wr_data[j*64 +: 64] !== write_word(j)) $fatal(1,"HP0 backend write data mismatch beat=%0d",j);
      backend_writes<=backend_writes+1;
    end
  end

  task automatic send_w(input integer n);
    integer watchdog;
    begin
      @(negedge clk); wdata=write_word(n); wlast=n==7; wvalid=1;
      watchdog=0;
      do begin
        @(posedge clk); watchdog=watchdog+1;
        if(watchdog>2000) $fatal(1,"HP0 W setup timeout");
      end while(!wready);
      @(negedge clk); wvalid=0;
    end
  endtask

  initial begin : scenario
    integer n, watchdog;
    #1; por_n=0; sys_n=0;
    repeat(25) @(negedge clk);
    por_n=1; sys_n=1;
    repeat(10) @(negedge clk);
    resetgen.fpga_soft_reset(32'b0);
    repeat(20) @(negedge clk);
    if(hp_resetn !== 1 || fclk_resetn !== 1) $fatal(1,"VIP reset initialization failed");
    hp0.set_latency_type(2'b10);
    for(n=0;n<8;n=n+1) rd_data[n*64 +: 64]=read_word(n);
    fork
      begin
        @(negedge clk); arvalid=1;
        watchdog=0;
        do begin
          @(posedge clk); watchdog=watchdog+1;
          if(watchdog>2000) $fatal(1,"HP0 AR timeout");
        end while(!arready);
        @(negedge clk); arvalid=0;
      end
      begin
        @(negedge clk); awvalid=1;
        do @(posedge clk); while(!awready);
        @(negedge clk); awvalid=0;
        send_w(0); send_w(1);
      end
      begin
        wait(rd_req === 1);
        @(negedge clk); rd_valid=1;
        @(negedge clk); rd_valid=0;
      end
    join
    watchdog=0;
    while(req_count<1 || !rvalid) begin
      @(negedge clk); watchdog=watchdog+1;
      if(watchdog>2000) $fatal(1,"HP0 did not present pending read response");
    end
    if(ar_count!=1 || aw_count!=1 || w_count!=2 || r_count!=0 || b_count!=0)
      $fatal(1,"HP0 simultaneous pending setup failed");
    $display("HP0_VIP_BOTH_PENDING read_requests=%0d write_beats=%0d",req_count,w_count);
    reset_monitor=1;
    resetgen.fpga_soft_reset(32'h1);
    repeat(25) @(negedge clk);
    if(fclk_resetn !== 0 || hp_resetn !== 1) $fatal(1,"HP0 reset domains not independent");
    $display("HP0_VIP_FCLK_ASSERTED hp_resetn=%b fclk_resetn=%b",hp_resetn,fclk_resetn);
    resetgen.fpga_soft_reset(32'b0);
    repeat(10) @(negedge clk);
    reset_monitor=0;
    rready=1; bready=1;
    for(n=2;n<8;n=n+1) send_w(n);
    watchdog=0;
    while(r_count<8 || b_count<1 || backend_writes<1) begin
      @(negedge clk); watchdog=watchdog+1;
      if(watchdog>3000) $fatal(1,"HP0 retained transaction completion timeout R=%0d B=%0d WR=%0d",r_count,b_count,backend_writes);
    end
    repeat(30) @(negedge clk);
    if(ar_count!=1 || aw_count!=1 || w_count!=8 || r_count!=8 || b_count!=1 || backend_writes!=1)
      $fatal(1,"HP0 duplicate/dropped transaction");
    $display("HP0_VIP_PENDING_SURVIVES_FCLK_RESET_PASS");
    $finish;
  end
  initial begin #300000; $fatal(1,"HP0 global watchdog"); end
endmodule
