`timescale 1ns/1ps
module tb_screen_control;
 reg clk=0;always #10 clk=~clk;
 reg rst=1,start=0,clear=0,sample=0,blocked=0;reg [1:0] eyes=3;
 reg [7:0] ratio0=128,ratio1=128;reg [9:0] x0=100,x1=200;
 wire [2:0] mode,mask;wire settled,valid,stale,armed,commit;
 wire [4:0] n;wire [1:0] dir,ed;wire [3:0] reason,progress;wire [15:0] seq;
 screen_control #(.MS_CYCLES(10),.SETTLE_MS(4),.CAL_TIMEOUT_MS(100),.CAL_SAMPLES(4),.DWELL_MS(12),.RELEASE_MS(5),.STALL_MS(30)) dut(
  clk,rst,clear,start,1'b0,sample,1'b1,blocked,eyes,ratio0,ratio1,x0,x1,9'd100,9'd100,
  mode,settled,n,mask,dir,valid,stale,reason,progress,armed,commit,seq,ed,,,,,,);
 integer events=0;always @(posedge clk)if(commit)events=events+1;
 task tick;begin @(negedge clk);end endtask
 task feed(input integer a,b);begin ratio0=a;ratio1=b;sample=1;tick();sample=0;repeat(9)tick();end endtask
 task calibrate(input bit collapsed);begin
  start=1;tick();start=0;
  for(integer slot=1;slot<=3;slot=slot+1)begin
   wait(mode==slot&&settled);tick();
   repeat(4)feed(collapsed?128:slot==1?100:slot==2?128:156,collapsed?128:slot==1?100:slot==2?128:156);
  end
  feed(128,128);
 end endtask
 initial begin
  repeat(5)tick();rst=0;
  repeat(5)feed(100,100);if(valid||events)$fatal(1,"uncalibrated action");
  calibrate(0);if(mode!=4||mask!=7)$fatal(1,"guided calibration");
  repeat(20)feed(100,100);if(events!=1||ed!=1||armed)$fatal(1,"left confirm %d",events);
  repeat(20)feed(100,100);if(events!=1)$fatal(1,"repeated confirm");
  eyes=0;repeat(5)feed(128,128);eyes=3;repeat(20)feed(156,156);if(events!=1)$fatal(1,"occlusion rearmed");
  repeat(10)feed(128,128);repeat(20)feed(156,156);if(events!=2||ed!=3)$fatal(1,"center release/right confirm");
  feed(100,156);if(valid||reason!=4)$fatal(1,"binocular disagreement");
  x0=130;feed(128,128);if(valid||reason!=3)$fatal(1,"head motion accepted");x0=100;
  eyes=1;feed(128,128);if(valid||reason!=2)$fatal(1,"single-eye accepted");eyes=3;
  repeat(5)feed(128,128);blocked=1;tick();if(valid)$fatal(1,"snapshot not immediate");blocked=0;
  repeat(320)tick();if(!stale||valid)$fatal(1,"camera stall");
  calibrate(1);if(mode!=5||valid||mask!=0)$fatal(1,"collapsed refs accepted");
  start=1;tick();start=0;feed(100,100);if(n!=0)$fatal(1,"sample before settling");
  wait(settled);tick();feed(100,100);feed(128,128);if(n!=0)$fatal(1,"unstable calibration accumulated");
  repeat(1050)tick();if(mode!=5||valid)$fatal(1,"calibration timeout not rejected");
  start=1;tick();start=0;
  for(integer slot=1;slot<=3;slot=slot+1)begin
   wait(mode==slot&&settled);tick();repeat(4)feed(slot==1?156:slot==2?128:100,slot==1?156:slot==2?128:100);
  end
  repeat(20)feed(156,156);if(mode!=4||ed!=1||events!=3)$fatal(1,"mirrored calibration direction");
  $display("PASS tb_screen_control: guided calibration, settle, binocular agreement, head-motion gate, dwell, release, snapshot, stall, bad/unstable/timeout calibration, mirror orientation");$finish;
 end
 initial begin #1000000;$fatal(1,"control timeout");end
endmodule
