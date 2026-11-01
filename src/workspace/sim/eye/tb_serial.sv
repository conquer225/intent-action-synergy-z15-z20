`timescale 1ns/1ps
module tb_serial;
 reg clk=0;always #10 clk=~clk;
 reg rst=1,rx=1;wire tx;
 wire [1:0] cal;wire clear,changed;wire [8:0] x;wire [7:0] y,w,h,th;
 wire req,rel;wire [16:0] addr;
 serial_control #(.REPORT_CYCLES(200),.UART_DIV(16)) dut(
  clk,rst,rx,tx,2'd1,2'd0,2'd1,1'b1,1'b1,1'b0,1'b1,1'b0,1'b0,
  3'd7,9'd135,16'd197,16'd1,16'h5640,8'd164,cal,clear,changed,x,y,w,h,th,req,1'b0,rel,addr,8'b0);
 wire [7:0] observed;wire observed_valid;
 uart #(.CLKS_PER_BIT(16)) monitor(clk,rst,tx,observed,observed_valid,8'b0,1'b0,,);
 reg [8*61-1:0] expected={"EYE L V1 F1 C7 A0 X087 N00C5 QA4 E0001 DL S0 I5640 R1 !0 K0",8'h0d,8'h0a};
 integer chars=0,changes=0,cal_seen=0;
 always @(posedge clk)begin
  if(changed)changes=changes+1;
  if(cal!=0)cal_seen=cal;
  if(observed_valid&&chars<61)begin
   if(observed!==expected[487:480])$fatal(1,"status byte %d got=%x expected=%x",chars,observed,expected[487:480]);
   expected={expected[479:0],8'b0};chars=chars+1;
  end
 end
 task byte_out(input [7:0] value);
  begin
   @(negedge clk);rx=0;repeat(16)@(negedge clk);
   for(integer n=0;n<8;n=n+1)begin rx=value[n];repeat(16)@(negedge clk);end
   rx=1;repeat(18)@(negedge clk);
  end
 endtask
 initial begin
  repeat(5)@(negedge clk);rst=0;
  byte_out("l");if(cal_seen!=1)$fatal(1,"calibration command");
  byte_out(8'ha5);byte_out(0);byte_out(130);byte_out(90);byte_out(80);byte_out(40);byte_out(70);byte_out(8'he6);byte_out(8'h5a);
  if(changes!=1||x!=130||y!=90||th!=70)$fatal(1,"ROI packet");
  byte_out(8'ha5);byte_out(0);byte_out(130);byte_out(90);byte_out(80);byte_out(40);byte_out(70);byte_out(0);byte_out(8'h5a);
  if(changes!=1)$fatal(1,"bad checksum accepted");
  wait(chars==61);$display("PASS tb_serial: exact status line, calibration, ROI packet, checksum rejection");$finish;
 end
 initial begin #2000000;$fatal(1,"serial timeout");end
endmodule
