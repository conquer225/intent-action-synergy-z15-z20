`timescale 1ns/1ps
// Verilog module-reference wrapper; AXI-Lite + frame-atomic held-data mailbox.
module live_osd #(parameter integer WIDTH=1280,HEIGHT=720,PIXEL_HZ=75000000)(
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET aresetn, FREQ_HZ 100000000" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *) input wire aclk,
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *) input wire aresetn,
    input wire [7:0] s_axi_awaddr, input wire [2:0] s_axi_awprot, input wire s_axi_awvalid, output wire s_axi_awready,
    input wire [31:0] s_axi_wdata, input wire [3:0] s_axi_wstrb, input wire s_axi_wvalid, output wire s_axi_wready,
    output reg [1:0] s_axi_bresp, output reg s_axi_bvalid, input wire s_axi_bready,
    input wire [7:0] s_axi_araddr,input wire [2:0] s_axi_arprot,input wire s_axi_arvalid,output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,output reg s_axi_rvalid,input wire s_axi_rready,
    (* X_INTERFACE_PARAMETER = "FREQ_HZ 75000000" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 pix_clk CLK" *) input wire pix_clk,
    input wire cam_vsync,
    input wire [23:0] in_data,input wire in_de,in_hsync,in_vsync,in_hblank,in_vblank,in_field,
    output wire [23:0] out_data,output wire out_de,out_hsync,out_vsync,out_hblank,out_vblank,out_field
);
    reg [31:0] shadow[0:31];
    // Separate held bank: software can prepare the next update while this is pending.
    reg [1023:0] held_data;
    reg request_toggle,ack_toggle;
    (* ASYNC_REG="TRUE" *) reg [1:0] ack_sync,req_sync;
    (* ASYNC_REG="TRUE" *) reg [1:0] pix_reset_sync;
    (* ASYNC_REG="TRUE" *) reg [1:0] cam_sync;
    reg cam_prev,vsync_prev;
    reg [31:0] camera_count;
    wire [31:0] display_count;
    wire [287:0] stimulus_stats;
    reg [287:0] stimulus_held;
    (* ASYNC_REG="TRUE" *) reg [287:0] stimulus_meta,stimulus_sync;
    reg [31:0] display_gray;
    (* ASYNC_REG="TRUE" *) reg [31:0] display_gray_meta,display_gray_sync;
    wire busy=request_toggle!=ack_sync[1];
    wire pix_resetn=pix_reset_sync[1];
    wire apply=(req_sync[1]!=ack_toggle) && in_vsync && !vsync_prev;
    reg aw_pending,w_pending;reg [7:0] write_addr;reg [31:0] write_data;reg [3:0] write_strb;
    assign s_axi_awready=!aw_pending && !s_axi_bvalid;
    assign s_axi_wready=!w_pending && !s_axi_bvalid;
    assign s_axi_arready=!s_axi_rvalid;
    function automatic [31:0] gray_to_binary(input [31:0] gray);
        integer k;begin gray_to_binary[31]=gray[31];for(k=30;k>=0;k=k-1)gray_to_binary[k]=gray_to_binary[k+1]^gray[k];end
    endfunction
    integer i,b;
    always @(posedge aclk)begin
        if(!aresetn)begin
            request_toggle<=0;ack_sync<=0;held_data<=0;aw_pending<=0;w_pending<=0;write_addr<=0;write_data<=0;write_strb<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;
            cam_sync<=0;cam_prev<=0;camera_count<=0;display_gray_meta<=0;display_gray_sync<=0;
            stimulus_meta<=0;stimulus_sync<=0;
            for(i=0;i<32;i=i+1)shadow[i]<=0;
        end else begin
            ack_sync<={ack_sync[0],ack_toggle};
            cam_sync<={cam_sync[0],cam_vsync};cam_prev<=cam_sync[1];
            if(cam_sync[1]&&!cam_prev)camera_count<=camera_count+1'b1;
            display_gray_meta<=display_gray;display_gray_sync<=display_gray_meta;
            stimulus_meta<=stimulus_held;stimulus_sync<=stimulus_meta;
            if(s_axi_awready && s_axi_awvalid)begin write_addr<=s_axi_awaddr;aw_pending<=1;end
            if(s_axi_wready && s_axi_wvalid)begin write_data<=s_axi_wdata;write_strb<=s_axi_wstrb;w_pending<=1;end
            if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
            if(aw_pending && w_pending && !s_axi_bvalid)begin
                aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if(write_addr[1:0]!=0 || write_addr>=128)s_axi_bresp<=2;
                else if(write_addr==8)begin
                    if(write_strb[0] && write_data[0])begin
                        if(busy)s_axi_bresp<=2;
                        else begin
                            for(i=0;i<32;i=i+1)held_data[i*32+:32]<=shadow[i];
                            request_toggle<=!request_toggle;
                        end
                    end
                end else if(write_addr>=32)begin
                    for(b=0;b<4;b=b+1)if(write_strb[b])shadow[write_addr[6:2]][b*8+:8]<=write_data[b*8+:8];
                end else s_axi_bresp<=2;
            end
            if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
            if(s_axi_arready && s_axi_arvalid)begin
                s_axi_rvalid<=1;s_axi_rresp<=0;
                case(s_axi_araddr)
                    0:s_axi_rdata<=32'h4f534438;
                    4:s_axi_rdata<={31'b0,busy};
                    8:s_axi_rdata<=0;
                    12:s_axi_rdata<=gray_to_binary(display_gray_sync);
                    16:s_axi_rdata<=camera_count;
                    default:begin
                        if(s_axi_araddr>=128 && s_axi_araddr<=160 && s_axi_araddr[1:0]==0)
                            s_axi_rdata<=stimulus_sync[(s_axi_araddr-128)*8+:32];
                        else if(s_axi_araddr[1:0]!=0 || s_axi_araddr>=128 || s_axi_araddr<32)begin s_axi_rdata<=0;s_axi_rresp<=2;end
                        else s_axi_rdata<=shadow[s_axi_araddr[6:2]];
                    end
                endcase
            end
        end
    end
    always @(posedge pix_clk or negedge aresetn)begin
        if(!aresetn)pix_reset_sync<=0;else pix_reset_sync<={pix_reset_sync[0],1'b1};
    end
    always @(posedge pix_clk)begin
        if(!pix_resetn)begin req_sync<=0;ack_toggle<=0;vsync_prev<=0;display_gray<=0;stimulus_held<=0;end
        else begin
            display_gray<=(display_count>>1)^display_count;
            req_sync<={req_sync[0],request_toggle};vsync_prev<=in_vsync;
            if(apply)begin ack_toggle<=req_sync[1];stimulus_held<=stimulus_stats;end
        end
    end
    live_osd_core #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.PIXEL_HZ(PIXEL_HZ)) renderer(
        .clk(pix_clk),.resetn(pix_resetn),.in_data(in_data),.in_de(in_de),.in_hsync(in_hsync),.in_vsync(in_vsync),
        .in_hblank(in_hblank),.in_vblank(in_vblank),.in_field(in_field),.apply(apply),.settings(held_data),
        .out_data(out_data),.out_de(out_de),.out_hsync(out_hsync),.out_vsync(out_vsync),
        .out_hblank(out_hblank),.out_vblank(out_vblank),.out_field(out_field),.frame_count(display_count),.stimulus_stats(stimulus_stats));
endmodule
