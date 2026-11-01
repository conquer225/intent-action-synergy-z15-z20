`timescale 1ns/1ps
module tb_core;
 reg clk=0;always #10 clk=~clk;
 reg rst=1,config_changed=0,wv=0;reg [27:0] word=0;
 wire sample,fv;wire [8:0] cx;wire [15:0] count;wire [7:0] contrast;
 eye_features features(clk,rst,config_changed,wv,word,9'd100,8'd80,8'd100,8'd60,8'd64,sample,fv,cx,count,contrast);
 reg gs=0,gvalid=0,clear=0;reg [8:0] gx=0;reg [1:0] cal=0;
 wire [1:0] direction,ca,ed;wire valid,ce,commit,stale;wire [2:0] calibrated;wire [8:0] lx,mx,rx;wire [15:0] seq;
 gaze_control #(.STALL_CYCLES(100),.DWELL_FRAMES(4),.RELEASE_FRAMES(3)) control(clk,rst,clear,gs,gvalid,gx,cal,direction,valid,calibrated,ca,ce,lx,mx,rx,commit,ed,seq,stale);
 integer events=0;
 always @(posedge clk)if(commit)events=events+1;
 task tick;begin @(negedge clk);end endtask
 task gaze(input integer x,input bit good);begin tick();gx=x;gvalid=good;gs=1;tick();gs=0;tick();end endtask
 task calibration(input integer slot,input integer x);begin tick();cal=slot;tick();cal=0;repeat(8)gaze(x,1);end endtask
 task frame(input integer pupil_x,input integer kind);
  integer x,y;reg [7:0] g;
  begin
   for(y=0;y<240;y=y+1)for(x=0;x<320;x=x+1)begin
    g=180;
    if(kind==1)g=10;
    else if(kind==2)g=180;
    else if(kind==3)begin if(x>=120&&x<=180&&y==110)g=16;end
    else if((x-pupil_x)*(x-pupil_x)+(y-110)*(y-110)<=64)g=16;
    tick();word={2'b00,x[8:0],y[7:0],1'b0,g};wv=1;
   end
   tick();word={2'b11,26'b0};tick();wv=0;
   wait(sample);tick();
  end
 endtask
 initial begin
  repeat(5)tick();rst=0;
  // First marker discards partial startup frame.
  tick();word={2'b11,26'b0};wv=1;tick();wv=0;
  frame(135,0);if(!fv||cx!=135||count!=197)$fatal(1,"pupil centroid/count %d %d valid=%d",cx,count,fv);
  frame(166,0);if(!fv||cx!=166)$fatal(1,"right pupil centroid");
  frame(150,1);if(fv)$fatal(1,"black obstruction accepted");
  frame(150,2);if(fv)$fatal(1,"blank frame accepted");
  frame(150,3);if(fv)$fatal(1,"thin eyelid line accepted");
  // No calibration => no action.
  repeat(8)gaze(120,1);if(valid||events)$fatal(1,"uncalibrated action");
  tick();cal=1;tick();cal=0;
  repeat(12)begin gaze(120,1);gaze(132,1);end
  if(calibrated[0]||ca!=1)$fatal(1,"unstable calibration accepted");
  repeat(8)gaze(120,1);
  if(!calibrated[0]||ca!=0||lx!=120)$fatal(1,"stable calibration recovery");
  calibration(1,120);calibration(2,145);calibration(3,170);
  gaze(145,1);if(calibrated!=7||!valid||direction!=2)$fatal(1,"calibration failed");
  repeat(10)gaze(120,1);if(events!=1||ed!=1)$fatal(1,"left dwell failed/repeated %d",events);
  repeat(5)gaze(120,0);repeat(6)gaze(170,1);if(events!=1)$fatal(1,"invalid rearmed action");
  repeat(3)gaze(145,1);repeat(5)gaze(170,1);if(events!=2||ed!=3)$fatal(1,"release/right dwell");
  gaze(132,1);if(valid)$fatal(1,"ambiguous midpoint accepted");
  repeat(110)tick();if(!stale||valid)$fatal(1,"stall remained valid");
  clear=1;tick();clear=0;
  // Reversed camera orientation is calibrated, not hard-coded.
  calibration(1,170);calibration(2,145);calibration(3,120);
  gaze(170,1);if(direction!=1)$fatal(1,"mirrored calibration wrong");
  calibration(2,170);gaze(170,1);if(!ce||valid)$fatal(1,"collapsed calibration accepted");
  $display("PASS tb_core: frame centroid, obstruction, calibration stability, mirror, dwell, release, timeout");$finish;
 end
 initial begin #20000000;$fatal(1,"test timeout");end
endmodule
