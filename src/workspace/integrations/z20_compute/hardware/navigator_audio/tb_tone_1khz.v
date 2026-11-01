`timescale 1ns/1ps

module tb_tone_1khz;
    reg clk = 0;
    reg rst_n = 0;
    reg sample_tick = 0;
    wire signed [15:0] sample;
    integer i;
    tone_1khz dut(.clk(clk), .rst_n(rst_n), .sample_tick(sample_tick), .sample(sample));
    always #5 clk = ~clk;

    task tick;
        begin
            @(negedge clk); sample_tick = 1;
            @(negedge clk); sample_tick = 0;
            #1;
        end
    endtask

    initial begin
        repeat (2) @(negedge clk);
        rst_n = 1;
        if (sample !== 16'sd2048) $fatal(1, "positive start");
        for (i = 0; i < 24; i = i + 1) tick();
        if (sample !== -16'sd2048) $fatal(1, "negative half cycle");
        for (i = 0; i < 24; i = i + 1) tick();
        if (sample !== 16'sd2048) $fatal(1, "48-sample cycle");
        rst_n = 0;
        @(negedge clk);
        if (sample !== 16'sd2048) $fatal(1, "reset phase");
        $display("TONE_1KHZ_PASS");
        $finish;
    end
endmodule
