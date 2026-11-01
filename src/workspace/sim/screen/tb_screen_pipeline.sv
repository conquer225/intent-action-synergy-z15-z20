`timescale 1ns/1ps
module tb_screen_pipeline;
 reg sys=0,cam=0;always #10 sys=~sys;always #10.416 cam=~cam;
 reg reset_n=0,vs=0,hr=0,rx=1;reg [7:0] data=0;tri1 sda;wire tx;
 z15_screen_top dut(.sys_clk(sys),.reset_n(reset_n),.cam_pclk(cam),.cam_vsync(vs),.cam_href(hr),.cam_data(data),.cam_sda(sda),.uart_rx(rx),.uart_tx(tx));
 defparam dut.serial_i.UART_DIV=8;
 defparam dut.serial_i.REPORT_CYCLES=100000;
 defparam dut.capture_i.WARM_FRAMES=2;
 defparam dut.gaze_i.SETTLE_MS=2;
 defparam dut.gaze_i.CAL_SAMPLES=4;
 defparam dut.gaze_i.DWELL_MS=2;
 defparam dut.gaze_i.RELEASE_MS=2;
 wire [7:0] observed;wire ov;
 uart #(.CLKS_PER_BIT(8)) monitor(sys,!reset_n,tx,observed,ov,8'b0,1'b0,,);
 integer lines=0,events=0;
 always @(posedge sys)begin
  if(ov&&observed==10)lines=lines+1;
  if(dut.commit)events=events+1;
 end
 task ctick;begin @(negedge cam);end endtask
 task boundary;begin vs=1;repeat(20)ctick();vs=0;repeat(20)ctick();end endtask
 task send(input [7:0] b);begin
  @(negedge sys);rx=0;repeat(8)@(negedge sys);
  for(integer n=0;n<8;n=n+1)begin rx=b[n];repeat(8)@(negedge sys);end
  rx=1;repeat(10)@(negedge sys);
 end endtask
 task packet(input [7:0] slot,input [15:0] x);reg [7:0] sum;begin
  sum=slot^x[15:8]^x[7:0]^200^64^32^70^140;
  send(8'hb5);send(slot);send(x[15:8]);send(x[7:0]);send(0);send(200);send(64);send(32);send(70);send(140);send(sum);send(8'h5a);
  repeat(15000)@(negedge sys);
 end endtask
 task frame(input integer gaze,shift,input bit black);
  integer dx,dy;reg [5:0] g;
  begin
   ctick();
   for(integer y=0;y<480;y=y+1)begin
    hr=1;
    for(integer x=0;x<640;x=x+1)begin
     g=25;dy=y-216;
     dx=x-(x<320?256:384)-shift;
     if(dx*dx*64+dy*dy*625<=40000)g=50;
     if((dx-gaze)*(dx-gaze)+dy*dy<=25)g=4;
     if(black)g=0;
     data={5'b0,g[5:3]};ctick();data={g[2:0],5'b0};ctick();
    end
    hr=0;repeat(10)ctick();
   end
   boundary();repeat(220)ctick();
  end
 endtask
 initial begin
  repeat(20)ctick();reset_n=1;force dut.ready=1;
  repeat(100)ctick();boundary();repeat(3)frame(0,0,0);
  packet(0,224);packet(1,352);
  if(dut.configured!=3)$fatal(1,"ROI config not acknowledged");
  frame(0,0,0);frame(0,0,0);if(dut.ev!=3)$fatal(1,"VGA features invalid");
  send("a");
  for(integer stage=1;stage<=3;stage=stage+1)begin
   wait(dut.mode==stage&&dut.settled);repeat(4)frame(stage==1?-8:stage==2?0:8,0,0);
   $display("pipeline: calibrated stage %0d at %t",stage,$time);
  end
  if(dut.mode!=4||dut.calibrated!=7)$fatal(1,"calibration sequence failed");
  repeat(5)frame(-8,0,0);if(events!=1||dut.event_direction!=1)$fatal(1,"left confirm %d",events);
  repeat(2)frame(-8,6,0);if(events!=1||dut.direction!=1)$fatal(1,"translation or repeated event");
  repeat(5)frame(0,0,0);repeat(5)frame(8,0,0);
  if(events!=2||dut.event_direction!=3)$fatal(1,"center rearm/right event");
  frame(0,0,1);if(dut.valid)$fatal(1,"occlusion accepted");
  if(lines<10)$fatal(1,"no UART status");
  if(dut.frames_i.preview[108*320+128]!==8'd0)$fatal(1,"decimated frame path");
  $display("PASS tb_screen_pipeline: VGA DVP, real async FIFO, dual-eye relative features, UART setup, HDMI calibration, translated eyes, left/right events, occlusion, decimated preview");$finish;
 end
 initial begin #700000000;$fatal(1,"screen pipeline timeout");end
endmodule
