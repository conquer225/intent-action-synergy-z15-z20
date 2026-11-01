`timescale 1ns/1ps
// 75 MHz / 48 kHz = 1562.5. Alternating 1562/1563-cycle intervals
// produce exactly 48 ticks per 75000 pixels (the HDMI ACR interval).
module audio_sample_tick (
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 clk_pixel CLK", X_INTERFACE_PARAMETER="FREQ_HZ 75000000" *)
    input wire clk_pixel,
    input wire reset,
    output wire sample_enable
);
    reg [26:0] phase = 0;
    assign sample_enable = !reset && phase >= 74952000;
    always @(posedge clk_pixel) begin
        if (reset) phase <= 0;
        else if (sample_enable) phase <= phase + 48000 - 75000000;
        else phase <= phase + 48000;
    end
endmodule
