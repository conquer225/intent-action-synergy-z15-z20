`timescale 1ns/1ps
module hdmi_audio_tx (
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 clk_pixel CLK", X_INTERFACE_PARAMETER="FREQ_HZ 75000000" *) input wire clk_pixel,
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 clk_pixel_x5 CLK", X_INTERFACE_PARAMETER="FREQ_HZ 375000000" *) input wire clk_pixel_x5,
    input wire sample_enable,
    input wire reset,
    input wire [23:0] rgb,
    input wire hsync,
    input wire vsync,
    input wire de,
    input wire [15:0] sample_left,
    input wire [15:0] sample_right,
    output wire timing_locked,
    output wire [2:0] tmds_data_p,
    output wire [2:0] tmds_data_n,
    (* X_INTERFACE_IGNORE="TRUE" *) output wire tmds_clk_p,
    (* X_INTERFACE_IGNORE="TRUE" *) output wire tmds_clk_n
);
    wire [29:0] words;
    wire [3:0] serialized;
    hdmi_external_video video (.clk_pixel(clk_pixel), .sample_enable(sample_enable), .reset(reset),
        .rgb(rgb), .hsync(hsync), .vsync(vsync), .de(de),
        .sample_left(sample_left), .sample_right(sample_right),
        .timing_locked(timing_locked), .tmds_words(words));
    genvar c;
    generate for (c = 0; c < 3; c = c + 1) begin: lanes
        serializer_10_to_1 serial (.reset(reset), .paralell_clk(clk_pixel),
            .serial_clk_5x(clk_pixel_x5), .paralell_data(words[c*10+:10]), .serial_data_out(serialized[c]));
        OBUFDS #(.IOSTANDARD("TMDS_33")) output_pair (.I(serialized[c]), .O(tmds_data_p[c]), .OB(tmds_data_n[c]));
    end endgenerate
    // Preserve the clock lane phase/polarity of the board vendor's transmitter.
    serializer_10_to_1 serial_clock (.reset(reset), .paralell_clk(clk_pixel),
        .serial_clk_5x(clk_pixel_x5), .paralell_data(10'b1111100000), .serial_data_out(serialized[3]));
    OBUFDS #(.IOSTANDARD("TMDS_33")) clock_pair (.I(serialized[3]), .O(tmds_clk_p), .OB(tmds_clk_n));
endmodule
