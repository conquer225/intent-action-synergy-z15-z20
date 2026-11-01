`timescale 1ns/1ps
// Requires the candidate MMCM's exact 150 MHz output, NOT PS FCLK1:
// legacy HWH requests 150 MHz there but reports 142.857132 MHz actual.
// The candidate clock plan is verified by verify_clocks.tcl. Divide by 3125.
module audio_sample_clock (
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 clk_150m CLK", X_INTERFACE_PARAMETER="FREQ_HZ 150000000" *) input wire clk_150m,
    input wire reset,
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 clk_sample CLK", X_INTERFACE_PARAMETER="FREQ_HZ 48000" *) output wire clk_sample
);
    reg [11:0] count = 0;
    reg divided = 0;
    always @(posedge clk_150m) begin
        if (reset) begin count <= 0; divided <= 0; end
        else begin
            count <= count == 3124 ? 12'd0 : count + 1'b1;
            divided <= count >= 1562;
        end
    end
    BUFG sample_clock_buffer (.I(divided), .O(clk_sample));
endmodule
