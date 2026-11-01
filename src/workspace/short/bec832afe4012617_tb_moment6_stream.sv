module tb_moment6_stream;
    logic clk = 0;
    always #5 clk <= ~clk;
    logic rst_n = 0, valid_i = 0, start_i = 0, last_i = 0;
    logic result_ready_i = 1;
    logic signed [95:0] sample_i = '0;
    wire result_valid_o, ready_o;
    wire [15:0] count_o;
    wire signed [287:0] sums_o;
    wire signed [1007:0] cross_o;
    moment6_stream dut(.*);

    task automatic send(input bit first, input bit last, input integer seed);
        @(negedge clk);
        valid_i = 1;
        start_i = first;
        last_i = last;
        for (int c = 0; c < 6; c++)
            sample_i[16*c +: 16] = 16'(seed + c);
        @(posedge clk);
        #1;
        if (result_valid_o !== last)
            $fatal(1, "result framing mismatch");
        @(negedge clk);
        valid_i = 0;
        start_i = 0;
        last_i = 0;
    endtask

    initial begin
        repeat (3) @(negedge clk);
        rst_n = 1;
        send(1, 0, 1);
        repeat (2) @(negedge clk);
        send(0, 1, -2);
        if (count_o !== 2) $fatal(1, "first count mismatch");
        for (int c = 0; c < 6; c++) begin
            if ($signed(sums_o[48*c +: 48]) !== (2*c - 1))
                $fatal(1, "sum[%0d] mismatch", c);
        end
        // (0,0): 1^2+(-2)^2 = 5; (0,1): 1*2+(-2)*(-1) = 4.
        if ($signed(cross_o[0 +: 48]) !== 5) $fatal(1, "gram[0,0]");
        if ($signed(cross_o[48 +: 48]) !== 4) $fatal(1, "gram[0,1]");
        result_ready_i = 0;
        valid_i = 1;
        start_i = 1;
        sample_i = '1;
        repeat (3) begin
            @(posedge clk);
            #1;
            if (ready_o !== 0 || result_valid_o !== 1 || count_o !== 2 ||
                $signed(cross_o[0 +: 48]) !== 5)
                $fatal(1, "backpressure changed pending result");
        end
        @(negedge clk);
        valid_i = 0;
        start_i = 0;
        result_ready_i = 1;
        send(1, 1, 7);
        if (count_o !== 1 || $signed(sums_o[0 +: 48]) !== 7 ||
            $signed(cross_o[0 +: 48]) !== 49)
            $fatal(1, "second frame did not clear first");
        send(1, 0, 3);
        @(negedge clk);
        rst_n = 0;
        @(posedge clk);
        #1;
        if (result_valid_o !== 0 || count_o !== 0 || sums_o !== 0 || cross_o !== 0)
            $fatal(1, "mid-frame reset mismatch");
        $display("PASS moment6_stream framing, sums, products, stall, backpressure, mid-frame reset");
        $finish;
    end
endmodule
