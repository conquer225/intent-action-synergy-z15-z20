`timescale 1ns/1ps
module tb_stream_history;
  reg clk=0;always #5 clk=~clk;
  reg reset=1,de=0,hs=0,vs=0;reg [3:0] mode=2;reg [23:0] rgb=0;
  wire [23:0] out;wire ode,ohs,ovs;
  reg [23:0] golden[0:2047];integer n=0,w=0,frame_id,i,j;reg [23:0] value;
  vision_stream_pixels #(.WIDTH(16),.HEIGHT(8)) dut(.clk(clk),.reset(reset),.enable(1'b1),.mode(mode),
    .in_rgb(rgb),.in_de(de),.in_hsync(hs),.in_vsync(vs),.out_rgb(out),.out_de(ode),.out_hsync(ohs),.out_vsync(ovs));
  always @(posedge clk)begin
    #1;if(!reset && ode)begin
      if(out!==golden[n])$fatal(1,"history %0d mode %0d got %h expected %h",n,mode,out,golden[n]);
      n=n+1;
    end
  end
  initial begin
    repeat(4)@(negedge clk);reset=0;
    for(frame_id=0;frame_id<10;frame_id=frame_id+1)begin
      mode=frame_id<3?2:(frame_id<6?8:3);vs=1;repeat(10000)@(negedge clk);vs=0;
      for(j=0;j<8;j=j+1)begin
        for(i=0;i<16;i=i+1)begin
          @(negedge clk);de=1;
          if(frame_id==0)begin rgb=0;value=0;end
          else if(frame_id==1)begin rgb=24'hffffff;value=24'hbeffff;end
          else if(frame_id==2)begin rgb=0;value=24'h3ffeff;end
          else if(frame_id<6)begin
            rgb=i<8?24'h101010:24'h202020;
            value=frame_id==3?rgb:(i<8?24'h000000:24'hffffff);
          end else if(frame_id<8)begin rgb=24'hffffff;value=24'h1f1f1f;end
          else if(frame_id==8)begin rgb=0;value=24'had90ff;end
          else begin rgb=0;value=0;end
          golden[w]=value;w=w+1;
        end
        @(negedge clk);de=0;hs=1;repeat(7)@(negedge clk);hs=0;
      end
      repeat(30)@(negedge clk);
    end
    if(n!=1280)$fatal(1,"lost pixels %0d",n);
    $display("STREAM_HISTORY_PASS moving pixels, reset, frame-history reuse and previous-frame equalization");$finish;
  end
  initial begin #2000000;$fatal(1,"timeout");end
endmodule
