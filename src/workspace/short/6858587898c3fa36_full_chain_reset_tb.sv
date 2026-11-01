`timescale 1ns/1ps
`define PS dut.processing_system7_0.inst

module full_chain_reset_tb;
  import axi_vip_pkg::*;
  reg ps_clk=0, por_n=1, sys_n=1;
  always #15 ps_clk=~ps_clk;
  wire ps_clk_pin=ps_clk, por_pin=por_n, sys_pin=sys_n;
  filter_candidate dut (
    .FIXED_IO_0_ps_clk(ps_clk_pin), .FIXED_IO_0_ps_porb(por_pin),
    .FIXED_IO_0_ps_srstb(sys_pin)
  );
  wire clk=dut.processing_system7_0_FCLK_CLK0;
  // Test-only slow response profile creates a repeatable overlapping R/W window.
  // Not a timing estimate for a physical HP port; vendor source is unchanged.
  defparam dut.processing_system7_0.inst.S_AXI_HP0.afi_rd_max=2000;
  localparam [31:0] DMA=32'h40400000, GPIO=32'h41200000;
  localparam integer IDLE=0, RUNNING=1, DRAINING=2, LOCKED=3;
  integer state=IDLE, frame=0, stream_count=0, published=0, submissions=0, resets=0;
  integer reads_pending=0, writes_pending=0, hp_reads=0, hp_writes=0, hp_wbeats=0;
  integer frame_rbeats=0, frame_wbeats=0, frame_ar=0, frame_aw=0;
  integer backend_mismatches=0;
  reg guard_enabled=0, reset_authorized=0, rejected=0;
  reg [63:0] inputs[0:239], expected[0:239];
  reg [31:0] tx_address=32'h00100000, rx_address=32'h00200000;
  axi_ready_gen stall_ready, read_ready, release_ready;

  always @(posedge clk) begin
    if (`PS.S_AXI_HP0_AWVALID && `PS.S_AXI_HP0_AWREADY)
      $display("HP_AW addr=%h len=%0d size=%0d burst=%0d id=%h",`PS.S_AXI_HP0_AWADDR,`PS.S_AXI_HP0_AWLEN+1,`PS.S_AXI_HP0_AWSIZE,`PS.S_AXI_HP0_AWBURST,`PS.S_AXI_HP0_AWID);
    if (`PS.S_AXI_HP0_WVALID && `PS.S_AXI_HP0_WREADY)
      $display("HP_W data=%h strb=%h last=%b id=%h",`PS.S_AXI_HP0_WDATA,`PS.S_AXI_HP0_WSTRB,`PS.S_AXI_HP0_WLAST,`PS.S_AXI_HP0_WID);
    if (`PS.S_AXI_HP0_BVALID && `PS.S_AXI_HP0_BREADY)
      $display("HP_B id=%h resp=%b t=%0t",`PS.S_AXI_HP0_BID,`PS.S_AXI_HP0_BRESP,$time);
  end
  always @(posedge `PS.net_sw_clk) begin
    if (`PS.S_AXI_HP0.WR_DATA_VALID_DDR)
      $display("HP_BACKEND_WR addr=%h bytes=%0d strb=%h first=%h ack=%b",`PS.S_AXI_HP0.WR_ADDR,`PS.S_AXI_HP0.WR_BYTES,`PS.S_AXI_HP0.WR_DATA_STRB,`PS.S_AXI_HP0.WR_DATA[63:0],`PS.S_AXI_HP0.WR_DATA_ACK_DDR);
    if (`PS.ddrc.wr_req)
      $display("DDR_COMMIT addr=%h bytes=%0d strb=%h first=%h",`PS.ddrc.wr_addr,`PS.ddrc.wr_bytes,`PS.ddrc.wr_strb,`PS.ddrc.wr_data[63:0]);
  end

  always @(posedge clk) begin
    if (`PS.S_AXI_HP0_ARVALID && `PS.S_AXI_HP0_ARREADY) begin
      if(`PS.S_AXI_HP0_ARADDR !== tx_address+frame_ar*128 || `PS.S_AXI_HP0_ARLEN !== 15 || `PS.S_AXI_HP0_ARSIZE !== 3)
        $fatal(1,"HP read address/length mismatch");
      hp_reads<=hp_reads+1; frame_ar<=frame_ar+1;
    end
    if (`PS.S_AXI_HP0_AWVALID && `PS.S_AXI_HP0_AWREADY) begin
      if(`PS.S_AXI_HP0_AWADDR !== rx_address+frame_aw*128 || `PS.S_AXI_HP0_AWLEN !== 15 || `PS.S_AXI_HP0_AWSIZE !== 3)
        $fatal(1,"HP write address/length mismatch");
      hp_writes<=hp_writes+1; frame_aw<=frame_aw+1;
    end
    if (`PS.S_AXI_HP0_RVALID && `PS.S_AXI_HP0_RREADY) begin
      if(frame_rbeats>=80 || `PS.S_AXI_HP0_RDATA !== inputs[frame*80+frame_rbeats] || `PS.S_AXI_HP0_RLAST !== (frame_rbeats%16==15))
        $fatal(1,"HP input data mismatch frame=%0d word=%0d",frame,frame_rbeats);
      frame_rbeats<=frame_rbeats+1;
    end
    if (`PS.S_AXI_HP0_WVALID && `PS.S_AXI_HP0_WREADY) begin
      if (`PS.S_AXI_HP0_WSTRB !== 8'hff) $fatal(1,"HP write byte mask mismatch");
      if(frame_wbeats>=80 || `PS.S_AXI_HP0_WDATA !== expected[frame*80+frame_wbeats] || `PS.S_AXI_HP0_WLAST !== (frame_wbeats%16==15))
        $fatal(1,"HP output data mismatch frame=%0d word=%0d",frame,frame_wbeats);
      hp_wbeats<=hp_wbeats+1;
      frame_wbeats<=frame_wbeats+1;
    end
    case ({(`PS.S_AXI_HP0_ARVALID && `PS.S_AXI_HP0_ARREADY),
           (`PS.S_AXI_HP0_RVALID && `PS.S_AXI_HP0_RREADY && `PS.S_AXI_HP0_RLAST)})
      2'b10: reads_pending<=reads_pending+1;
      2'b01: reads_pending<=reads_pending-1;
    endcase
    case ({(`PS.S_AXI_HP0_AWVALID && `PS.S_AXI_HP0_AWREADY),
           (`PS.S_AXI_HP0_BVALID && `PS.S_AXI_HP0_BREADY)})
      2'b10: writes_pending<=writes_pending+1;
      2'b01: writes_pending<=writes_pending-1;
    endcase
    if(reads_pending<0 || writes_pending<0) $fatal(1,"unmatched HP response");
    if(`PS.S_AXI_HP0_RVALID && `PS.S_AXI_HP0_RREADY && `PS.S_AXI_HP0_RRESP !== 0)
      $fatal(1,"HP read response error");
    if(`PS.S_AXI_HP0_BVALID && `PS.S_AXI_HP0_BREADY && `PS.S_AXI_HP0_BRESP !== 0)
      $fatal(1,"HP write response error");
    if(dut.pf_filter_m_axis_TVALID && dut.pf_filter_m_axis_TREADY) begin
      if(stream_count>=80 || dut.pf_filter_m_axis_TDATA !== expected[frame*80+stream_count] ||
         dut.pf_filter_m_axis_TKEEP !== 8'hff || dut.pf_filter_m_axis_TLAST !== (stream_count==79))
        $fatal(1,"full filter stream mismatch frame=%0d word=%0d data=%h expected=%h",frame,stream_count,dut.pf_filter_m_axis_TDATA,expected[frame*80+stream_count]);
      stream_count<=stream_count+1;
    end
  end
  always @(negedge dut.pf_shell_reset_peripheral_aresetn) begin
    if(guard_enabled && (!reset_authorized || reads_pending!=0 || writes_pending!=0 || stream_count!=80))
      $fatal(1,"local reset occurred without proven complete drain");
  end

  task automatic wr(input [31:0] addr, input [31:0] value);
    reg [1:0] response;
    reg [2047:0] payload;
    begin
      payload=0; payload[31:0]=value;
      `PS.write_data(addr,4,payload,response);
      if(response !== 0) $fatal(1,"GP0 write response error at %h",addr);
    end
  endtask
  task automatic rd(input [31:0] addr, output reg [31:0] value);
    reg [1:0] response;
    reg [2047:0] payload;
    begin
      `PS.read_data(addr,4,payload,response);
      if(response !== 0) $fatal(1,"GP0 read response error at %h",addr);
      value=payload[31:0];
    end
  endtask
  task automatic configure;
    reg [31:0] status;
    begin
      wr(GPIO+4,0); wr(GPIO+12,32'hffffffff);
      wr(GPIO,1); rd(GPIO+8,status);
      if(status !== 32'h50460001) $fatal(1,"filter reset ABI mismatch %h",status);
      wr(GPIO,0); rd(GPIO+8,status);
      if(status !== 32'h50460000) $fatal(1,"filter release ABI mismatch %h",status);
      wr(DMA,1); wr(DMA+32'h30,1);
    end
  endtask
  task automatic prepare_frame(input integer number);
    integer n;
    reg [1023:0] payload;
    begin
      frame=number; stream_count=0;
      frame_rbeats=0; frame_wbeats=0; frame_ar=0; frame_aw=0;
      tx_address=32'h00100000+number*32'h1000;
      rx_address=32'h00200000+number*32'h1000;
      for(n=0;n<80;n=n+1) begin
        payload=0; payload[63:0]=inputs[number*80+n];
        `PS.write_mem(payload,tx_address+n*8,8);
        payload[63:0]=64'hdeadbeefdeadbeef;
        `PS.write_mem(payload,rx_address+n*8,8);
      end
    end
  endtask
  task automatic submit;
    begin
      if(state!=IDLE) begin
        rejected=1;
        $display("NEW_SUBMISSION_REJECTED state=%0d",state);
      end else begin
        state=RUNNING; submissions=submissions+1;
        wr(DMA+4,32'h7000); wr(DMA+32'h34,32'h7000);
        wr(DMA+32'h48,rx_address); wr(DMA+32'h58,640);
        wr(DMA+32'h18,tx_address); wr(DMA+32'h28,640);
      end
    end
  endtask
  task automatic completion(input integer limit, output reg complete);
    integer count;
    reg [31:0] a,b,status,length;
    begin
      complete=0;
      for(count=0;count<limit && !complete;count=count+1) begin
        rd(DMA+4,a); rd(DMA+32'h34,b); rd(GPIO+8,status);
        if((a|b)&32'h770 || status !== 32'h50460000) $fatal(1,"DMA/filter error while draining");
        if((a&32'h1002)==32'h1002 && (b&32'h1002)==32'h1002 &&
           reads_pending==0 && writes_pending==0 && stream_count==80 && frame_rbeats==80 && frame_wbeats==80 && !dut.pf_filter_m_axis_TVALID) begin
          rd(DMA+32'h58,length);
          if(length!==640) $fatal(1,"incomplete RX length %0d",length);
          complete=1;
        end
      end
      $display("FULL_COMPLETION complete=%b polls=%0d read_pending=%0d write_pending=%0d words=%0d",complete,count,reads_pending,writes_pending,stream_count);
    end
  endtask
  task automatic check_ddr;
    integer n,mismatches,first_bad;
    reg [1023:0] payload;
    begin
      mismatches=0; first_bad=-1;
      for(n=0;n<80;n=n+1) begin
        `PS.read_mem(rx_address+n*8,8,payload);
        if(payload[63:0] !== expected[frame*80+n]) begin
          if(first_bad<0) first_bad=n;
          mismatches=mismatches+1;
        end
      end
      if(mismatches>0) begin
        backend_mismatches=backend_mismatches+mismatches;
        $display("VIP_DDR_MISMATCH frame=%0d words=%0d first_bad=%0d",frame,mismatches,first_bad);
        if(!$test$plusargs("observe_backend")) $fatal(1,"DDR golden mismatch: full acceptance blocked");
      end else $display("FULL_DDR_GOLDEN_PASS frame=%0d words=80",frame);
      $display("FULL_FILTER_DMA_HP_PASS frame=%0d R=80 W=80 AXIS=80",frame);
    end
  endtask
  task automatic local_reset;
    integer count;
    begin
      if(state!=DRAINING || reads_pending!=0 || writes_pending!=0 || stream_count!=80)
        $fatal(1,"reset guard bypassed");
      reset_authorized=1;
      `PS.fpga_soft_reset(1);
      count=0;
      while(dut.pf_shell_reset_peripheral_aresetn !== 0) begin
        @(negedge clk); count=count+1;
        if(count>1000) $fatal(1,"PL reset assertion timeout");
      end
      repeat(25) @(negedge clk);
      if(`PS.net_axi_hp0_rstn !== 1) $fatal(1,"PL reset changed HP0 reset domain");
      `PS.fpga_soft_reset(0);
      count=0;
      while(dut.pf_shell_reset_peripheral_aresetn !== 1) begin
        @(negedge clk); count=count+1;
        if(count>1000) $fatal(1,"PL reset release timeout");
      end
      repeat(20) @(negedge clk);
      reset_authorized=0; resets=resets+1;
      configure(); state=IDLE;
      $display("GUARDED_LOCAL_RESET_PASS resets=%0d",resets);
    end
  endtask
  initial begin : scenario
    integer fd,n,r,ch,rc,count,saved_submissions;
    reg [39:0] value,golden;
    reg complete,stall_case;
    fd=$fopen("vectors.txt","r");
    if(!fd) $fatal(1,"missing golden vectors");
    for(n=0;n<240;n=n+1) begin
      rc=$fscanf(fd,"%d %d %h %h\n",r,ch,value,golden);
      if(rc!=4 || ch!=n%8 || r!=(n==0)) $fatal(1,"invalid continuous golden vectors");
      inputs[n]={{24{value[39]}},value}; expected[n]={{24{golden[39]}},golden};
    end
    $fclose(fd);
    #1; por_n=0; sys_n=0;
    repeat(25) @(negedge ps_clk);
    por_n=1; sys_n=1;
    repeat(30) @(negedge clk);
    `PS.fpga_soft_reset(0);
    wait(dut.pf_shell_reset_peripheral_aresetn===1);
    repeat(30) @(negedge clk);
    `PS.set_debug_level_info(0);
    `PS.S_AXI_HP0.set_latency_type(2);
    // Space read commands so a complete input frame cannot be prefetched before
    // the first filtered write. Backpressure uses the vendor VIP API, not force.
    read_ready=`PS.S_AXI_HP0.slv.rd_driver.create_ready("spaced_read_commands");
    read_ready.set_ready_policy(XIL_AXI_READY_GEN_OSC);
    read_ready.set_low_time(2000); read_ready.set_high_time(1);
    `PS.S_AXI_HP0.slv.rd_driver.set_arready_gen(read_ready);
    `PS.S_AXI_HP0.slv.wr_driver.set_forward_progress_timeout_value(2000000);
    configure(); guard_enabled=1;
    prepare_frame(0); submit(); completion(4000,complete);
    if(!complete) $fatal(1,"normal full-chain timeout");
    check_ddr(); published=published+1; state=IDLE;
    $display("FULL_NORMAL_BUS_PASS");

    stall_case=$test$plusargs("blocked");
    if(stall_case || $test$plusargs("transient_stall")) begin
      stall_ready=`PS.S_AXI_HP0.slv.wr_driver.create_ready("full_chain_stall");
      stall_ready.set_ready_policy(XIL_AXI_READY_GEN_SINGLE);
      stall_ready.set_low_time(stall_case ? 1000000 : 6000);
      stall_ready.set_high_time(1);
      release_ready=`PS.S_AXI_HP0.slv.wr_driver.create_ready("after_single_stall");
      release_ready.set_ready_policy(XIL_AXI_READY_GEN_NO_BACKPRESSURE);
      release_ready.set_low_time(0); release_ready.set_high_time(1);
      fork begin
        `PS.S_AXI_HP0.slv.wr_driver.send_wready(stall_ready);
        if(!stall_case) `PS.S_AXI_HP0.slv.wr_driver.send_wready(release_ready);
      end join_none
    end
    prepare_frame(1); submit();
    if(stall_case || $test$plusargs("transient_stall")) begin
      // An idle NO_BACKPRESSURE policy waits for its next accepted beat before
      // consuming the queued policy. Start DMA first, then prove the stall.
      count=0;
      while(frame_wbeats==0 || `PS.S_AXI_HP0_WREADY !== 0) begin
        @(negedge clk); count=count+1;
        if(count>30000) $fatal(1,"VIP write backpressure did not assert");
      end
      $display("FULL_WRITE_STALL_ASSERTED beats=%0d permanent=%b",frame_wbeats,stall_case);
    end
    count=0;
    while(reads_pending==0 || writes_pending==0) begin
      @(negedge clk); count=count+1;
      if(count>30000) $fatal(1,"full chain never had both HP directions outstanding");
    end
    $display("FULL_BOTH_INFLIGHT read_pending=%0d write_pending=%0d filter_words=%0d",reads_pending,writes_pending,stream_count);
    state=DRAINING; saved_submissions=submissions;
    submit();
    if(!rejected || submissions!=saved_submissions) $fatal(1,"draining accepted new batch");
    completion(stall_case ? 300 : 4000,complete);
    if(!complete) begin
      state=LOCKED;
      if(!stall_case) $fatal(1,"recoverable drain timeout");
      saved_submissions=submissions; rejected=0; submit();
      if(!rejected || submissions!=saved_submissions || resets!=0 || published!=1 || writes_pending==0)
        $fatal(1,"blocked controller freed/restarted/published");
      repeat(100) @(negedge clk);
      $display("FULL_BLOCKED_LOCKOUT_PASS submissions=%0d published=%0d resets=%0d retained_tx=%h retained_rx=%h backend_mismatches=%0d",submissions,published,resets,tx_address,rx_address,backend_mismatches);
      $finish;
    end
    check_ddr();
    $display("DRAINED_FRAME_DISCARDED published=%0d",published);
    local_reset();
    // Re-warmup starts from a reset filter, so use the first-frame golden again.
    prepare_frame(0); submit(); completion(4000,complete);
    if(!complete) $fatal(1,"post-reset full chain timeout");
    check_ddr(); published=published+1; state=IDLE;
    if(published!=2 || resets!=1 || submissions!=3) $fatal(1,"publication/reset count mismatch");
    $display("FULL_GUARDED_RECOVERY_PASS submissions=3 published=2 resets=1 backend_mismatches=%0d",backend_mismatches);
    $finish;
  end
  initial begin #20000000; $fatal(1,"full-chain global watchdog"); end
endmodule
`undef PS
