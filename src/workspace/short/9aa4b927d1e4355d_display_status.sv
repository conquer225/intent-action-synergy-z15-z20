`timescale 1ns/1ps
// Known libtobii_display ABI only: identity +0, scan count +12. The UI already
// draws into the framebuffer; this replacement does not invent other OSD registers.
module display_status #(
    parameter WIDTH=1280, HEIGHT=720, PIXEL_HZ=75000000
)(
    (* X_INTERFACE_PARAMETER = "FREQ_HZ 100000000, ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET aresetn" *)
    input wire aclk,
    input wire aresetn,
    input wire [7:0] s_axi_awaddr,
    input wire [2:0] s_axi_awprot,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,
    input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output wire [1:0] s_axi_bresp,
    output reg s_axi_bvalid,
    input wire s_axi_bready,
    input wire [7:0] s_axi_araddr,
    input wire [2:0] s_axi_arprot,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,
    output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid,
    input wire s_axi_rready,
    (* X_INTERFACE_PARAMETER="FREQ_HZ 75000000" *) input wire pix_clk,
    input wire cam_vsync,
    input wire [23:0] in_data,
    input wire in_de, in_hsync, in_vsync, in_hblank, in_vblank, in_field,
    output wire [23:0] out_data,
    output wire out_de, out_hsync, out_vsync, out_hblank, out_vblank, out_field
);
    assign out_data = in_data;
    assign {out_de,out_hsync,out_vsync,out_hblank,out_vblank,out_field} =
           {in_de,in_hsync,in_vsync,in_hblank,in_vblank,in_field};
    (* ASYNC_REG="TRUE" *) reg [1:0] pixel_reset;
    always @(posedge pix_clk or negedge aresetn) begin
        if (!aresetn) pixel_reset <= 0;
        else pixel_reset <= {pixel_reset[0],1'b1};
    end
    reg [31:0] scan_count = 0;
    reg previous_vsync = 0;
    always @(posedge pix_clk) begin
        if (!pixel_reset[1]) begin scan_count <= 0; previous_vsync <= 0; end
        else begin
            previous_vsync <= in_vsync;
            if (in_vsync && !previous_vsync) scan_count <= scan_count + 1'b1;
        end
    end
    wire [31:0] host_scan_count;
    // XPM has no reset port; its increment-only assertion also fires on the
    // legitimate reset-to-zero jump. Reset visibility is checked by the TB.
    xpm_cdc_gray #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .REG_OUTPUT(1),
        .SIM_ASSERT_CHK(0), .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(32)) scan_crossing (
        .src_clk(pix_clk), .src_in_bin(scan_count),
        .dest_clk(aclk), .dest_out_bin(host_scan_count));

    reg aw_pending, w_pending;
    assign s_axi_awready = !aw_pending && !s_axi_bvalid;
    assign s_axi_wready = !w_pending && !s_axi_bvalid;
    assign s_axi_arready = !s_axi_rvalid;
    assign s_axi_bresp = 2'b10;
    always @(posedge aclk) begin
        if (!aresetn) begin
            aw_pending <= 0; w_pending <= 0; s_axi_bvalid <= 0;
            s_axi_rvalid <= 0; s_axi_rresp <= 0; s_axi_rdata <= 0;
        end else begin
            if (s_axi_awready && s_axi_awvalid) aw_pending <= 1;
            if (s_axi_wready && s_axi_wvalid) w_pending <= 1;
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 0;
            if (aw_pending && w_pending && !s_axi_bvalid) begin
                aw_pending <= 0; w_pending <= 0; s_axi_bvalid <= 1;
            end
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 0;
            if (s_axi_arready && s_axi_arvalid) begin
                s_axi_rvalid <= 1; s_axi_rresp <= 0;
                case (s_axi_araddr)
                    8'h00: s_axi_rdata <= 32'h4f534438;
                    8'h0c: s_axi_rdata <= host_scan_count;
                    default: begin s_axi_rdata <= 0; s_axi_rresp <= 2'b10; end
                endcase
            end
        end
    end
endmodule
