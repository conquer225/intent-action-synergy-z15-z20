`timescale 1ns/1ps
module tb_screen_pixels;
 reg clk=0;always #10 clk=~clk;
 reg rst=1;reg [2:0] mode=1;reg valid=0;reg [1:0] direction=0;
 wire [16:0] addr;wire [23:0] rgb;wire de,hs,vs;wire [9:0] x,y;
 screen_pixels dut(clk,rst,8'd100,{10'd224,9'd200,8'd64,8'd32,8'd70,8'd140},
 {10'd352,9'd200,8'd64,8'd32,8'd70,8'd140},mode,direction,2'b11,2'd1,
 valid,1'b1,1'b0,1'b1,5'd0,4'd5,4'd8,addr,rgb,de,hs,vs,x,y);
 task save(input [255:0] name);
  integer f,n;begin
   f=$fopen(name,"w");$fwrite(f,"P3\n640 480\n255\n");n=0;
   @(negedge clk);wait(x==0&&y==0&&de);
   while(n<307200)begin
    @(negedge clk);
    if(de)begin
     if(addr>=76800)$fatal(1,"display address out of range");
     $fwrite(f,"%0d %0d %0d\n",rgb[23:16],rgb[15:8],rgb[7:0]);n=n+1;
    end
   end
   $fclose(f);
  end endtask
 initial begin
  repeat(5)@(negedge clk);rst=0;save("screen_calibration.ppm");
  mode=4;direction=3;valid=1;save("screen_run.ppm");
  mode=0;valid=0;save("screen_setup.ppm");
  $display("PASS tb_screen_pixels: active raster, bounded frame address, calibration/run/setup frame renders");$finish;
 end
 initial begin #70000000;$fatal(1,"pixels timeout");end
endmodule
