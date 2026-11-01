`timescale 1ns/1ps
module primary_sos_tb;
    reg clk=0, rst=1, in_valid=0, out_ready=0;
    reg [2:0] in_channel=0;
    reg signed [39:0] in_data=0;
    wire in_ready, out_valid, overflow;
    wire [2:0] out_channel;
    wire signed [39:0] out_data;
    primary_sos_core dut(.*);
    always #5 clk=~clk; // Simulation only; NOT a verified board clock constraint.
    integer fd, scanned, do_reset, ch, count=0, cycles, max_cycles=0, j;
    reg signed [39:0] value, expected;
    reg old_overflow;
    task reset_core;
        begin
            @(negedge clk); rst=1; in_valid=0; out_ready=0;
            repeat (2) @(negedge clk);
            if (out_valid || overflow) $fatal(1,"Reset did not clear output/fault");
            rst=0;
        end
    endtask

    initial begin
        reset_core();
        // Abort an accepted, partially processed word; no stale output may survive.
        @(negedge clk); in_channel=3; in_data=40'sd1234567; in_valid=1;
        @(negedge clk); in_valid=0;
        repeat (3) @(negedge clk);
        reset_core();
        repeat (30) begin
            @(negedge clk);
            if (out_valid) $fatal(1,"Output survived aborted transaction");
        end
        fd=$fopen("vectors.txt","r");
        if (!fd) $fatal(1,"Missing vectors");
        while (!$feof(fd)) begin
            scanned=$fscanf(fd,"%d %d %h %h\n",do_reset,ch,value,expected);
            if (scanned != 4) $fatal(1,"Malformed vector line");
            if (do_reset) reset_core();
            repeat (count%3) @(negedge clk);
            while (!in_ready) @(negedge clk);
            in_data=value; in_channel=ch; in_valid=1; out_ready=0;
            @(negedge clk); in_valid=0;
            cycles=0;
            while (!out_valid) begin
                @(negedge clk); cycles=cycles+1;
                if (cycles>60) $fatal(1,"Core latency exceeded pipelined bound");
            end
            if (cycles>max_cycles) max_cycles=cycles;
            if (out_data !== expected || out_channel !== ch[2:0])
                $fatal(1,"Mismatch word %0d ch %0d got %h expected %h",count,ch,out_data,expected);
            old_overflow=overflow;
            // Backpressure: all visible output fields must remain stable.
            for (j=0; j<(count%7); j=j+1) begin
                @(negedge clk);
                if (!out_valid || out_data !== expected || out_channel !== ch[2:0] ||
                    overflow !== old_overflow || in_ready)
                    $fatal(1,"Output/backpressure violation");
            end
            out_ready=1;
            @(negedge clk); out_ready=0;
            count=count+1;
        end
        $fclose(fd);
        if (!overflow) $fatal(1,"Saturation stress did not set fault flag");
        reset_core();
        $display("RTL_PASS words=%0d max_processing_cycles=%0d reset_abort=PASS backpressure=PASS saturation=PASS",count,max_cycles);
        $finish;
    end
    initial begin
        #500000000;
        $fatal(1,"Global simulation timeout");
    end
endmodule
