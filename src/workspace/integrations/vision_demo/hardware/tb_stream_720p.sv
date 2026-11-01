`timescale 1ns/1ps
module tb_stream_720p;
  reg clk=0;always #6.666 clk=~clk;
  reg reset=1,de=0,hs=0,vs=0,enable=1;reg [23:0] rgb=0;
  wire [23:0] out;wire ode,ohs,ovs;
  reg [23:0] golden[0:4];reg [4:0] dp=0,hp=0,vp=0;
  integer frame_id,x,y,k,inputs=0,outputs=0;
  vision_stream_pixels dut(.clk(clk),.reset(reset),.enable(enable),.mode(4'd4),
    .in_rgb(rgb),.in_de(de),.in_hsync(hs),.in_vsync(vs),.out_rgb(out),.out_de(ode),.out_hsync(ohs),.out_vsync(ovs));
  always @(posedge clk)begin
    if(reset)begin dp=0;hp=0;vp=0;end
    else begin
      for(k=4;k>0;k=k-1)golden[k]=golden[k-1];
      golden[0]=!enable?rgb:rgb==24'hff0000 ? 24'h4d4d4d:rgb==24'h00ff00 ? 24'h959595:rgb==24'h0000ff ? 24'h1d1d1d:24'hffffff;
      dp={dp[3:0],de};hp={hp[3:0],hs};vp={vp[3:0],vs};
      if(de)inputs=inputs+1;
      #1;
      if({ode,ohs,ovs}!=={dp[4],hp[4],vp[4]})$fatal(1,"720p sync mismatch");
      if(ode)begin if(out!==golden[4])$fatal(1,"720p pixel mismatch %0d",outputs);outputs=outputs+1;end
    end
  end
  initial begin
    repeat(8)@(negedge clk);reset=0;
    for(frame_id=0;frame_id<2;frame_id=frame_id+1)begin
      enable=frame_id==0;
      for(y=0;y<750;y=y+1)for(x=0;x<1650;x=x+1)begin
        @(negedge clk);de=x<1280 && y<720;hs=x>=1390 && x<1430;vs=y>=724 && y<729;
        case(x%4)0:rgb=24'hff0000;1:rgb=24'h00ff00;2:rgb=24'h0000ff;3:rgb=24'hffffff;endcase
      end
    end
    @(negedge clk);de=0;repeat(10)@(negedge clk);
    if(inputs!=1843200 || outputs!=inputs)$fatal(1,"720p pixel count %0d %0d",inputs,outputs);
    $display("STREAM_720P_PASS 1843200 pixels at 75MHz / 1650x750 timing, exact pixel and sync alignment");$finish;
  end
  initial begin #40000000;$fatal(1,"720p timeout");end
endmodule
