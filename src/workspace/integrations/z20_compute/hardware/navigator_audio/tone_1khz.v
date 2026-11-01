// One 48-sample period at 48 kHz. Initial board tone is deliberately low level.
module tone_1khz(
    input clk,
    input rst_n,
    input sample_tick,
    output wire signed [15:0] sample
);
    reg [5:0] phase;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            phase <= 6'd0;
        else if (sample_tick)
            phase <= phase == 6'd47 ? 6'd0 : phase + 1'b1;
    end
    assign sample = phase < 6'd24 ? 16'sd2048 : -16'sd2048;
endmodule
