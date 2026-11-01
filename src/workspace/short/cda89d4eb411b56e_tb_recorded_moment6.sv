module tb_recorded_moment6;
    logic clk = 0;
    always #5 clk <= ~clk;
    logic rst_n = 0, valid_i = 0, start_i = 0, last_i = 0;
    logic result_ready_i = 1;
    logic signed [95:0] sample_i = '0;
    wire result_valid_o, ready_o;
    wire [15:0] count_o;
    wire signed [287:0] sums_o;
    wire signed [1007:0] cross_o;
    logic [95:0] samples [0:2999];
    logic [47:0] golden [0:26];
    moment6_stream dut(.*);

    initial begin
        $readmemh("test_vectors.hex", samples);
        $readmemh("golden.hex", golden);
        repeat (3) @(negedge clk);
        rst_n = 1;
        for (int k = 0; k < 3000; k++) begin
            @(negedge clk);
            if (ready_o !== 1) $fatal(1, "unexpected input backpressure at %0d", k);
            valid_i = 1;
            start_i = (k == 0);
            last_i = (k == 2999);
            sample_i = samples[k];
            @(posedge clk);
            #1;
            if (result_valid_o !== (k == 2999)) $fatal(1, "framing at %0d", k);
        end
        if (count_o !== 3000) $fatal(1, "sample count");
        for (int c = 0; c < 6; c++)
            if (sums_o[48*c +: 48] !== golden[c]) $fatal(1, "recorded sum[%0d]", c);
        for (int p = 0; p < 21; p++)
            if (cross_o[48*p +: 48] !== golden[6+p]) $fatal(1, "recorded gram[%0d]", p);
        $display("PASS recorded 3000 samples, 6 sums, 21 cross-products");
        $finish;
    end
endmodule
