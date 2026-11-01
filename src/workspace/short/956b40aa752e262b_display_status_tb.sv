`timescale 1ns/1ps
module display_status_tb;
    reg host=0, pixel=0, resetn=0;
    always #5 host=!host;
    always #(20.0/3.0) pixel=!pixel;
    reg [7:0] araddr=0;
    reg arvalid=0, rready=0, vsync=0;
    reg awvalid=0, wvalid=0, bready=0;
    wire arready,rvalid,awready,wready,bvalid;
    wire [1:0] rresp,bresp;
    wire [31:0] rdata;
    reg [23:0] rgb=0;
    reg [5:0] signals=0;
    wire [23:0] out_rgb;
    wire [5:0] out_signals;
    display_status dut (.aclk(host),.aresetn(resetn),.s_axi_awaddr(8'd0),.s_axi_awprot(3'd0),
        .s_axi_awvalid(awvalid),.s_axi_awready(awready),.s_axi_wdata(32'h12345678),.s_axi_wstrb(4'hf),
        .s_axi_wvalid(wvalid),.s_axi_wready(wready),.s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
        .s_axi_araddr(araddr),.s_axi_arprot(3'd0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),
        .pix_clk(pixel),.cam_vsync(1'b0),.in_data(rgb),.out_data(out_rgb),
        .in_de(signals[0]),.in_hsync(signals[1]),.in_vsync(vsync),
        .in_hblank(signals[3]),.in_vblank(signals[4]),.in_field(signals[5]),
        .out_de(out_signals[0]),.out_hsync(out_signals[1]),.out_vsync(out_signals[2]),
        .out_hblank(out_signals[3]),.out_vblank(out_signals[4]),.out_field(out_signals[5]));
    task read_reg(input [7:0] address,input [31:0] expected,input [1:0] response);
        begin
            @(negedge host); araddr=address; arvalid=1;
            @(posedge host); while(!arready) @(posedge host);
            @(negedge host); arvalid=0;
            wait(rvalid);
            repeat(4) begin
                @(negedge host);
                if (!rvalid || rdata !== expected || rresp !== response) $fatal(1,"OSD register/backpressure mismatch");
            end
            rready=1; @(negedge host); rready=0;
        end
    endtask
    initial begin
        #100 resetn=1;
        #200;
        read_reg(0,32'h4f534438,0);
        read_reg(12,0,0);
        for(int i=0;i<3;i++) begin
            @(negedge pixel); vsync=1;
            repeat(5) @(negedge pixel);
            vsync=0;
            repeat(8) @(negedge pixel);
        end
        read_reg(12,3,0);
        read_reg(4,0,2);
        for(int i=0;i<64;i++) begin
            rgb=24'(i*7919); signals=6'(i);
            #1;
            if(out_rgb !== rgb || out_signals !== {signals[5:3],vsync,signals[1:0]}) $fatal(1,"Video path changed");
        end
        @(negedge host); awvalid=1;
        @(negedge host); awvalid=0;
        repeat(3) @(negedge host);
        if(bvalid) $fatal(1,"Write response arrived before data");
        wvalid=1; @(negedge host); wvalid=0;
        wait(bvalid);
        repeat(3) begin
            @(negedge host);
            if(!bvalid || bresp !== 2) $fatal(1,"OSD write refusal/backpressure failed");
        end
        bready=1; @(negedge host); bready=0;
        read_reg(0,32'h4f534438,0);
        read_reg(12,3,0);
        resetn=0; #200; resetn=1; #200;
        read_reg(12,0,0);
        $display("DISPLAY_STATUS_PASS identity=PASS frames=3 CDC=PASS video_passthrough=PASS AXI_backpressure=PASS reset=PASS");
        $finish;
    end
    initial begin #10000; $fatal(1,"Timeout"); end
endmodule
