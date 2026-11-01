`timescale 1ns/1ps
// Full top-level DVP -> real XPM asynchronous FIFO -> features -> calibration -> UART.
// Sensor electrical/init bus checked separately by tb_sccb; ready is forced here.
module tb_pipeline;
 reg sys=0,cam=0;always #10 sys=~sys;always #10.416 cam=~cam;
 reg reset_n=0,vs=0,hr=0,uart_rx=1;reg [7:0] data=0;tri1 sda;
 wire tx;
 z15_eye_top dut(.sys_clk(sys),.reset_n(reset_n),.cam_pclk(cam),.cam_vsync(vs),.cam_href(hr),.cam_data(data),.cam_sda(sda),.uart_rx(uart_rx),.uart_tx(tx));
 defparam dut.serial_i.UART_DIV=16;
 defparam dut.serial_i.REPORT_CYCLES=2000;
 defparam dut.gaze_i.DWELL_FRAMES=4;
 defparam dut.gaze_i.RELEASE_FRAMES=3;
 wire [7:0] byte_in;wire byte_valid;
 uart #(.CLKS_PER_BIT(16)) monitor(sys,!reset_n,tx,byte_in,byte_valid,8'b0,1'b0,,);
 integer lines=0,commits=0;
 always @(posedge sys)begin
  if(byte_valid&&byte_in==10)lines=lines+1;
  if(dut.commit)commits=commits+1;
 end
 task ctick;begin @(negedge cam);end endtask
 task boundary;begin vs=1;repeat(20)ctick();vs=0;repeat(20)ctick();end endtask
 task send(input [7:0] b);begin
  @(negedge sys);uart_rx=0;repeat(16)@(negedge sys);
  for(integer n=0;n<8;n=n+1)begin uart_rx=b[n];repeat(16)@(negedge sys);end
  uart_rx=1;repeat(18)@(negedge sys);
 end endtask
 task frame(input integer center,input bit black);
  reg [5:0] g;
  begin
   // UART tasks return in the system domain; align stimulus before driving DVP.
   ctick();
   for(integer y=0;y<240;y=y+1)begin
    hr=1;
    for(integer x=0;x<320;x=x+1)begin
     g=((x-center)*(x-center)+(y-116)*(y-116)<=49)?6'd4:6'd45;
     if(black)g=0;
     data={5'b0,g[5:3]};ctick();data={g[2:0],5'b0};ctick();
    end
    hr=0;repeat(10)ctick();
   end
   boundary();repeat(40)ctick();
  end
 endtask
 initial begin
  repeat(20)ctick();reset_n=1;force dut.ready=1'b1;
  repeat(100)ctick();boundary();repeat(11)frame(160,0);
  $display("pipeline: capture warmup complete at %t",$time);
  if(!dut.feature_valid||dut.cx!=160)$fatal(1,"DVP/FIFO centroid failure %d %d",dut.feature_valid,dut.cx);
  send("l");repeat(8)frame(140,0);
  send("c");repeat(8)frame(160,0);
  send("r");repeat(8)frame(180,0);
  $display("pipeline: calibration complete at %t",$time);
  repeat(5)frame(140,0);
  if(dut.calibrated!=7||commits!=1||dut.event_direction!=1)$fatal(1,"pipeline left calibration/event mask=%d commits=%d dir=%d refs=%d/%d/%d",dut.calibrated,commits,dut.event_direction,dut.left_x,dut.center_x,dut.right_x);
  repeat(4)frame(140,0);if(commits!=1)$fatal(1,"pipeline repeat event");
  repeat(3)frame(160,0);repeat(5)frame(180,0);
  if(commits!=2||dut.event_direction!=3)$fatal(1,"pipeline right event");
  frame(160,1);if(dut.valid)$fatal(1,"pipeline occlusion");
  if(lines<10)$fatal(1,"no UART reports");
  $display("PASS tb_pipeline: DVP/async FIFO/centroid/UART calibration/one-shot events/occlusion");$finish;
 end
 initial begin #300000000;$fatal(1,"pipeline timeout");end
endmodule
