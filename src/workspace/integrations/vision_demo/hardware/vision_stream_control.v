`timescale 1ns/1ps
// SPDX-License-Identifier: MIT
// New VIS2 ABI. Mode request is held until a frame-boundary acknowledgment.
module vision_stream_control(
  (* X_INTERFACE_PARAMETER="FREQ_HZ 100000000, ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET aresetn" *) input wire aclk,
  input wire aresetn,
  input wire [7:0] s_axi_awaddr,input wire [2:0] s_axi_awprot,input wire s_axi_awvalid,output wire s_axi_awready,
  input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,input wire s_axi_wvalid,output wire s_axi_wready,
  output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
  input wire [7:0] s_axi_araddr,input wire [2:0] s_axi_arprot,input wire s_axi_arvalid,output wire s_axi_arready,
  output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,output reg s_axi_rvalid,input wire s_axi_rready,
  (* X_INTERFACE_PARAMETER="FREQ_HZ 75000000" *) input wire pix_clk,
  input wire cam_clk,cam_vsync,
  input wire [23:0] in_data,input wire in_de,in_hsync,in_vsync,in_hblank,in_vblank,in_field,
  output wire [23:0] out_data,output wire out_de,out_hsync,out_vsync,out_hblank,out_vblank,out_field
);
  wire pix_reset;
  xpm_cdc_async_rst #(.DEST_SYNC_FF(2),.INIT_SYNC_FF(0),.RST_ACTIVE_HIGH(1)) reset_crossing(
    .src_arst(!aresetn),.dest_clk(pix_clk),.dest_arst(pix_reset));
  reg [1:0] transfer;
  reg [4:0] request_config,applied_config;
  wire [4:0] destination_config;
  wire source_received,destination_request;
  reg previous_vs;reg [4:0] pixel_config;
  reg acknowledge;
  wire commit=destination_request && !acknowledge && in_vsync && !previous_vs;
  xpm_cdc_handshake #(.DEST_EXT_HSK(1),.DEST_SYNC_FF(2),.SRC_SYNC_FF(2),.WIDTH(5),.INIT_SYNC_FF(0),.SIM_ASSERT_CHK(1)) config_crossing(
    .src_clk(aclk),.src_in(request_config),.src_send(transfer==1),.src_rcv(source_received),
    .dest_clk(pix_clk),.dest_out(destination_config),.dest_req(destination_request),.dest_ack(acknowledge));
  reg [31:0] frames,pixels;
  wire [31:0] host_frames,host_pixels;
  always @(posedge pix_clk)begin
    if(pix_reset)begin pixel_config<=0;previous_vs<=0;frames<=0;pixels<=0;acknowledge<=0;end
    else begin
      previous_vs<=in_vsync;
      if(commit)begin pixel_config<=destination_config;acknowledge<=1;end
      else if(!destination_request)acknowledge<=0;
      if(in_vsync && !previous_vs)frames<=frames+1'b1;
      if(in_de && pixel_config[4])pixels<=pixels+1'b1;
    end
  end
  xpm_cdc_gray #(.DEST_SYNC_FF(2),.REG_OUTPUT(1),.INIT_SYNC_FF(0),.SIM_ASSERT_CHK(0),.WIDTH(32)) frame_crossing(
    .src_clk(pix_clk),.src_in_bin(frames),.dest_clk(aclk),.dest_out_bin(host_frames));
  xpm_cdc_gray #(.DEST_SYNC_FF(2),.REG_OUTPUT(1),.INIT_SYNC_FF(0),.SIM_ASSERT_CHK(0),.WIDTH(32)) pixel_crossing(
    .src_clk(pix_clk),.src_in_bin(pixels),.dest_clk(aclk),.dest_out_bin(host_pixels));
  wire camera_sync;reg camera_previous;reg [31:0] camera_frames;
  // The retained camera IP gates VSYNC with its warm-up flag. Register that
  // source-domain expression before synchronizing it into the AXI domain.
  xpm_cdc_single #(.DEST_SYNC_FF(2),.INIT_SYNC_FF(0),.SRC_INPUT_REG(1),.SIM_ASSERT_CHK(0)) camera_crossing(
    .src_clk(cam_clk),.src_in(cam_vsync),.dest_clk(aclk),.dest_out(camera_sync));
  reg aw_pending,w_pending;reg [7:0] write_address;reg [31:0] write_data;reg [3:0] write_strobes;
  assign s_axi_awready=!aw_pending && !s_axi_bvalid;
  assign s_axi_wready=!w_pending && !s_axi_bvalid;
  assign s_axi_arready=!s_axi_rvalid;
  always @(posedge aclk)begin
    if(!aresetn)begin
      transfer<=0;request_config<=0;applied_config<=0;aw_pending<=0;w_pending<=0;
      s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
      camera_previous<=0;camera_frames<=0;
    end else begin
      camera_previous<=camera_sync;if(camera_sync && !camera_previous)camera_frames<=camera_frames+1'b1;
      if(transfer==1 && source_received)begin applied_config<=request_config;transfer<=2;end
      else if(transfer==2 && !source_received)transfer<=0;
      if(s_axi_awvalid && s_axi_awready)begin aw_pending<=1;write_address<=s_axi_awaddr;end
      if(s_axi_wvalid && s_axi_wready)begin w_pending<=1;write_data<=s_axi_wdata;write_strobes<=s_axi_wstrb;end
      if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
      if(aw_pending && w_pending && !s_axi_bvalid)begin
        aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=2'b10;
        if(write_address==8'h04 && write_strobes[0] && write_data[31:5]==0 && write_data[3:0]<=8 && transfer==0)begin
          request_config<=write_data[4:0];transfer<=1;s_axi_bresp<=0;
        end
      end
      if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
      if(s_axi_arvalid && s_axi_arready)begin
        s_axi_rvalid<=1;s_axi_rresp<=0;
        case(s_axi_araddr)
          8'h00:s_axi_rdata<=32'h56495332;
          8'h04:s_axi_rdata<={27'd0,applied_config};
          8'h08:s_axi_rdata<={30'd0,transfer};
          8'h0c:s_axi_rdata<=host_frames;
          8'h10:s_axi_rdata<=camera_frames;
          8'h14:s_axi_rdata<=host_pixels;
          8'h18:s_axi_rdata<=32'h050002d0;
          default:begin s_axi_rdata<=0;s_axi_rresp<=2'b10;end
        endcase
      end
    end
  end
  vision_stream_pixels pixels_pipeline(.clk(pix_clk),.reset(pix_reset),.enable(pixel_config[4]),.mode(pixel_config[3:0]),
    .in_rgb(in_data),.in_de(in_de),.in_hsync(in_hsync),.in_vsync(in_vsync),
    .out_rgb(out_data),.out_de(out_de),.out_hsync(out_hsync),.out_vsync(out_vsync));
  reg [4:0] hblank_pipe,vblank_pipe,field_pipe;
  always @(posedge pix_clk)begin
    if(pix_reset)begin hblank_pipe<=0;vblank_pipe<=0;field_pipe<=0;end
    else begin hblank_pipe<={hblank_pipe[3:0],in_hblank};vblank_pipe<={vblank_pipe[3:0],in_vblank};field_pipe<={field_pipe[3:0],in_field};end
  end
  assign out_hblank=hblank_pipe[4],out_vblank=vblank_pipe[4],out_field=field_pipe[4];
endmodule
