`timescale 1ns/1ps
module tb_audio_meter_cdc;
    reg audio_clk = 0;
    reg pixel_clk = 0;
    reg rst_n = 0;
    reg sample_valid = 0;
    reg signed [15:0] sample = 0;
    wire [7:0] level;
    integer i;
    audio_meter_cdc #(.BLOCK_SAMPLES(4), .COUNT_BITS(2)) dut(
        .audio_clk(audio_clk), .pixel_clk(pixel_clk), .rst_n(rst_n),
        .sample_valid(sample_valid), .sample(sample), .level(level)
    );
    always #10 audio_clk = ~audio_clk;
    always #3 pixel_clk = ~pixel_clk;
    task send_sample(input signed [15:0] value);
        begin
            @(negedge audio_clk); sample = value; sample_valid = 1;
            @(negedge audio_clk); sample_valid = 0;
        end
    endtask
    initial begin
        repeat (2) @(negedge audio_clk);
        rst_n = 1;
        send_sample(16'sd0);
        send_sample(-16'sd4096);
        send_sample(16'sd200);
        send_sample(16'sd0);
        repeat (8) @(negedge audio_clk);
        if (level !== 8'd128) $fatal(1, "first block peak");
        for (i = 0; i < 4; i = i + 1) send_sample(16'sd0);
        repeat (8) @(negedge audio_clk);
        if (level !== 8'd0) $fatal(1, "silence clears level");
        $display("AUDIO_METER_CDC_PASS");
        $finish;
    end
endmodule
