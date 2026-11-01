`timescale 1ns/1fs
module serializer_tb;
    logic pixel = 0, pixel5 = 0, reset = 1;
    always #(20.0/3.0) pixel = !pixel;
    always #(4.0/3.0) pixel5 = !pixel5;
    logic [9:0] word_in = 10'h001;
    wire data_out, clock_out;
    serializer_10_to_1 data_lane (.reset(reset), .paralell_clk(pixel),
        .serial_clk_5x(pixel5), .paralell_data(word_in), .serial_data_out(data_out));
    serializer_10_to_1 clock_lane (.reset(reset), .paralell_clk(pixel),
        .serial_clk_5x(pixel5), .paralell_data(10'b1111100000), .serial_data_out(clock_out));
    integer pattern = 0, stable_cycles = 0;
    always @(negedge pixel) if (!reset) begin
        stable_cycles <= stable_cycles + 1;
        if (stable_cycles == 39) begin
            pattern <= pattern + 1;
            stable_cycles <= 0;
            word_in <= pattern < 9 ? (10'd1 << (pattern+1)) : 10'((pattern+1)*197);
        end
    end
    logic previous_clock = 0;
    logic [9:0] recovered = 0;
    integer bit_index = -1, edge_count = 0, last_start = 0, checked = 0;
    always @(posedge pixel5 or negedge pixel5) begin
        // UNISIM OSERDESE2 OQ has a nonzero propagation delay.
        #0.2;
        if (!reset && $time > 2000) begin
            edge_count++;
            if (previous_clock && !clock_out) begin
                if (last_start && edge_count-last_start != 10) $fatal(1, "Clock lane is not 10 serial bits");
                last_start = edge_count;
                bit_index = 0;
            end else if (bit_index >= 0) bit_index++;
            if (bit_index >= 0 && bit_index < 10) recovered[bit_index] = data_out;
            if (bit_index == 9 && stable_cycles >= 6 && stable_cycles < 38) begin
                if (recovered !== word_in) $fatal(1, "Serial bit order/data mismatch got=%h expected=%h", recovered, word_in);
                checked++;
            end
            previous_clock = clock_out;
        end
    end
    initial begin
        #1005 reset = 0;
        #20000;
        if (checked < 900 || pattern < 30) $fatal(1, "Incomplete serializer coverage");
        $display("SERIALIZER_PASS checked_words=%0d patterns=%0d real_OSERDESE2=PASS clock_lane=PASS bit_order=PASS", checked, pattern);
        $finish;
    end
endmodule
