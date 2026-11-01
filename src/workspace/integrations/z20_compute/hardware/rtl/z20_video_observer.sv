// Read-only descriptor registers. AXI and passive taps share VDMA memory clock.
module z20_video_observer(
 (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 aclk CLK", X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET aresetn" *) input wire aclk,
 (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 aresetn RST", X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) input wire aresetn,
 input wire [7:0] s_axi_awaddr,s_axi_araddr,
 input wire s_axi_awvalid,s_axi_wvalid,s_axi_bready,s_axi_arvalid,s_axi_rready,
 input wire [31:0] s_axi_wdata,
 input wire [3:0] s_axi_wstrb,
 output wire s_axi_awready,s_axi_wready,s_axi_arready,
 output reg s_axi_bvalid,s_axi_rvalid,
 output wire [1:0] s_axi_bresp,
 output reg [1:0] s_axi_rresp,
 output reg [31:0] s_axi_rdata,
 input wire [31:0] cam0_awaddr,cam1_awaddr,
 input wire [7:0] cam0_awlen,cam1_awlen,
 input wire [2:0] cam0_awsize,cam1_awsize,
 input wire cam0_awvalid,cam1_awvalid,cam0_awready,cam1_awready,
 input wire cam0_bvalid,cam1_bvalid,cam0_bready,cam1_bready,
 input wire [1:0] cam0_bresp,cam1_bresp
);
 wire [1:0] wr[0:1],done[0:1];
 wire [31:0] epoch[0:1],seq[0:1];
 wire [1:0] wvalid,dvalid,fault,changed;
 z20_video_epoch #(.BASE(32'h01000000)) cam0(
 .clk(aclk),.reset_n(aresetn),.awvalid(cam0_awvalid),.awready(cam0_awready),
 .awaddr(cam0_awaddr),.awlen(cam0_awlen),.awsize(cam0_awsize),
 .bvalid(cam0_bvalid),.bready(cam0_bready),.bresp(cam0_bresp),
 .writer_index(wr[0]),.completed_index(done[0]),.write_epoch(epoch[0]),
 .completed_sequence(seq[0]),.writer_valid(wvalid[0]),.completed_valid(dvalid[0]),
 .fault(fault[0]),.event_changed(changed[0]));
 z20_video_epoch #(.BASE(32'h01000780)) cam1(
 .clk(aclk),.reset_n(aresetn),.awvalid(cam1_awvalid),.awready(cam1_awready),
 .awaddr(cam1_awaddr),.awlen(cam1_awlen),.awsize(cam1_awsize),
 .bvalid(cam1_bvalid),.bready(cam1_bready),.bresp(cam1_bresp),
 .writer_index(wr[1]),.completed_index(done[1]),.write_epoch(epoch[1]),
 .completed_sequence(seq[1]),.writer_valid(wvalid[1]),.completed_valid(dvalid[1]),
 .fault(fault[1]),.event_changed(changed[1]));
 reg [31:0] revision,flags[0:1],saved_epoch[0:1],saved_seq[0:1];
 reg [63:0] ticks,completed_ticks[0:1];
 wire [31:0] current_flags[0:1];
 assign current_flags[0]={20'b0,done[0],wr[0],5'b0,fault[0],dvalid[0],wvalid[0]};
 assign current_flags[1]={20'b0,done[1],wr[1],5'b0,fault[1],dvalid[1],wvalid[1]};
 wire descriptor_changed=(flags[0]!=current_flags[0] || flags[1]!=current_flags[1] ||
  saved_epoch[0]!=epoch[0] || saved_epoch[1]!=epoch[1] || saved_seq[0]!=seq[0] || saved_seq[1]!=seq[1]);
 reg address_seen,data_seen;
 assign s_axi_awready=aresetn && !address_seen && !s_axi_bvalid;
 assign s_axi_wready=aresetn && !data_seen && !s_axi_bvalid;
 assign s_axi_bresp=2'b10;
 assign s_axi_arready=aresetn && !s_axi_rvalid;
 integer i;
 always @(posedge aclk) begin
  if(!aresetn) begin
   revision<=0;ticks<=0;address_seen<=0;data_seen<=0;
   s_axi_bvalid<=0;s_axi_rvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;
   for(i=0;i<2;i=i+1) begin flags[i]<=0;saved_epoch[i]<=0;saved_seq[i]<=0;completed_ticks[i]<=0;end
  end else begin
   ticks<=ticks+1;
   if(descriptor_changed) revision<=revision+1;
   for(i=0;i<2;i=i+1) begin
    flags[i]<=current_flags[i];saved_epoch[i]<=epoch[i];saved_seq[i]<=seq[i];
    if(saved_seq[i]!=seq[i]) completed_ticks[i]<=ticks;
   end
   if(s_axi_awvalid && s_axi_awready) address_seen<=1;
   if(s_axi_wvalid && s_axi_wready) data_seen<=1;
   if(address_seen && data_seen && !s_axi_bvalid) begin
    s_axi_bvalid<=1;address_seen<=0;data_seen<=0;
   end
   if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
   if(s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
   if(s_axi_arvalid && s_axi_arready) begin
    s_axi_rvalid<=1;s_axi_rresp<=0;
    case(s_axi_araddr)
     'h00:s_axi_rdata<=32'h5a325643;
     'h04:s_axi_rdata<=1;
     'h08:s_axi_rdata<=revision;
     'h0c:s_axi_rdata<=142857132;
     'h10:s_axi_rdata<=flags[0];'h14:s_axi_rdata<=saved_epoch[0];'h18:s_axi_rdata<=saved_seq[0];
     'h1c:s_axi_rdata<=flags[1];'h20:s_axi_rdata<=saved_epoch[1];'h24:s_axi_rdata<=saved_seq[1];
     'h28:s_axi_rdata<=ticks[31:0];'h2c:s_axi_rdata<=ticks[63:32];
     'h30:s_axi_rdata<=completed_ticks[0][31:0];'h34:s_axi_rdata<=completed_ticks[0][63:32];
     'h38:s_axi_rdata<=completed_ticks[1][31:0];'h3c:s_axi_rdata<=completed_ticks[1][63:32];
     'h40:s_axi_rdata<=32'h01000000;'h44:s_axi_rdata<=2764800;
     'h48:s_axi_rdata<=3840;'h4c:s_axi_rdata<=720;'h50:s_axi_rdata<=1920;
     default:begin s_axi_rdata<=0;s_axi_rresp<=2;end
    endcase
   end
  end
 end
endmodule
