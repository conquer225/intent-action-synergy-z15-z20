`timescale 1ns/1ps
module tb_screen_serial;
 reg clk=0;always #10 clk=~clk;
 reg rst=1,rx=1;wire tx,start,preview,clear,changed;wire [50:0] box0,box1;wire [1:0] configured;
 screen_serial #(.REPORT_CYCLES(2000),.UART_DIV(8)) dut(
  clk,rst,rx,tx,2'd1,2'd3,2'd1,1'b1,1'b0,1'b1,1'b0,1'b0,1'b1,
  3'd4,3'd7,5'd0,4'd0,4'd0,8'h70,8'h71,16'd1,16'h5640,
  start,preview,clear,changed,box0,box1,configured,,1'b0,,,8'b0);
 wire [7:0] observed;wire ov;
 uart #(.CLKS_PER_BIT(8)) monitor(clk,rst,tx,observed,ov,8'b0,1'b0,,);
 reg [535:0] expected={"SCR L V1 F3 M4 C7 P00 T0 H0 G0 A1 X70 Y71 E0001 DL S0 I5640 R1 !0",8'h0d,8'h0a};
 integer n=0,changes=0,starts=0,acks0=0,acks1=0;reg [111:0] history=0;
 always @(posedge clk)begin
  if(changed)changes=changes+1;if(start)starts=starts+1;
  if(ov)begin
   history={history[103:0],observed};
   if(history=={"RCFG",8'h00,8'h00,8'he0,8'h00,8'hc8,8'h40,8'h20,8'h46,8'h8c,8'h82})acks0=acks0+1;
   if(history=={"RCFG",8'h01,8'h01,8'h60,8'h00,8'hc8,8'h40,8'h20,8'h46,8'h8c,8'h02})acks1=acks1+1;
   if(n<67)begin if(observed!==expected[535:528])$fatal(1,"status byte %d %x != %x",n,observed,expected[535:528]);expected={expected[527:0],8'b0};end
   n=n+1;
  end
 end
 task tick;begin @(negedge clk);end endtask
 task send(input [7:0] b);begin tick();rx=0;repeat(8)tick();for(integer i=0;i<8;i=i+1)begin rx=b[i];repeat(8)tick();end rx=1;repeat(10)tick();end endtask
 task packet(input [7:0] slot,input [15:0] x,input bit corrupt);
  reg [7:0] checksum;begin
   checksum=slot^x[15:8]^x[7:0]^0^200^64^32^70^140;
   send(8'hb5);send(slot);send(x[15:8]);send(x[7:0]);send(0);send(200);send(64);send(32);send(70);send(140);send(corrupt?checksum^1:checksum);send(8'h5a);
  end
 endtask
 initial begin
  repeat(5)tick();rst=0;send("a");if(starts)$fatal(1,"start before setup");wait(n>=67);
  packet(0,224,0);repeat(15000)tick();if(changes!=1||box0[50:41]!=224||acks0!=1)$fatal(1,"first eye packet/ACK");
  packet(1,352,0);repeat(15000)tick();if(changes!=2||configured!=3||acks1!=1)$fatal(1,"second eye packet/ACK");
  send("a");if(starts!=1)$fatal(1,"start missing");
  packet(0,360,0);repeat(15000)tick();if(changes!=2)$fatal(1,"overlapping eyes accepted");
  packet(0,224,1);repeat(15000)tick();if(changes!=2)$fatal(1,"bad checksum accepted");
  if(acks0!=1||acks1!=1)$fatal(1,"rejected configuration acknowledged");
  $display("PASS tb_screen_serial: exact versioned status and ACKs, dual-eye config, setup gating, overlap/checksum rejection");$finish;
 end
 initial begin #5000000;$fatal(1,"serial timeout");end
endmodule
