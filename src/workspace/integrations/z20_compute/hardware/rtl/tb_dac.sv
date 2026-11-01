`timescale 1ns/1ps
module tb_dac;
    reg clk=0, resetn=0, sample_tick=0, valid=0;
    reg [8:0] data=0;
    wire ready, sync, underrun;
    wire [7:0] dac;
    wire [31:0] count;
    always #5 clk=~clk;
    z20_dac_stream dut(clk,resetn,sample_tick,data,valid,ready,dac,sync,underrun,count);
    task tick(input bit strobe, input bit present, input [8:0] value,
              input [7:0] expected, input bit marker, input bit missing);
        @(negedge clk); sample_tick=strobe;valid=present;data=value;
        #1;
        if (ready !== strobe) $fatal(1,"ready must follow sample tick");
        @(posedge clk); #1;
        if (dac !== expected || sync !== marker || underrun !== missing)
            $fatal(1,"DAC output/marker/underrun mismatch");
    endtask
    initial begin
        repeat(2) @(posedge clk);
        @(negedge clk); resetn=1;
        // Frozen spectrum stream begins with a marker; no consume between ticks.
        tick(1,1,9'h1ff,255,1,0);
        tick(0,1,9'h005,255,1,0);
        tick(1,1,9'h005,5,0,0);
        // Analysis/producer may pause; converter timing always advances to midpoint.
        tick(1,0,9'h000,128,0,1);
        tick(0,0,9'h000,128,0,0);
        tick(1,0,9'h000,128,0,1);
        // Next complete source block can switch back to ordinary audio codes.
        tick(1,1,9'h080,128,0,0);
        tick(1,1,9'h0c0,192,0,0);
        if (count !== 2) $fatal(1,"underrun counter mismatch");
        $display("PASS: DAC sample timing, sweep sync, underrun and audio return");
        $finish;
    end
    initial begin #10000; $fatal(1,"watchdog"); end
endmodule
