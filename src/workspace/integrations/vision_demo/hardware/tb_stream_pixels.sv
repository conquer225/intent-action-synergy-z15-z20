`timescale 1ns/1ps
module tb_stream_pixels;
  reg clk=0; always #5 clk=~clk;
  reg reset=1, enable=1; reg [3:0] mode=4;
  reg [23:0] rgb=0; reg de=0,hs=0,vs=0;
  wire [23:0] out; wire ode,ohs,ovs;
  vision_stream_pixels #(.WIDTH(16),.HEIGHT(8)) dut(
    .clk(clk),.reset(reset),.enable(enable),.mode(mode),
    .in_rgb(rgb),.in_de(de),.in_hsync(hs),.in_vsync(vs),
    .out_rgb(out),.out_de(ode),.out_hsync(ohs),.out_vsync(ovs));
  integer n=0, input_n=0, output_n=0, i,j; reg [23:0] expected[0:2047];
  always @(posedge clk) if(!reset) begin
    if(de) begin
      expected[input_n] = !enable || mode==0 ? rgb :
        mode==4 || mode==6 ? 24'h4d4d4d : mode==5 ? 24'h000000 :
        mode==1 ? 24'h1f0000 :
        mode==2 ? 24'h7f0000 : mode==3 ? 24'h1f0000 :
        mode==7 && ((input_n%128)/16<2 || input_n%16<2) ? 24'h4d4d4d : 24'h000000;
      input_n=input_n+1;
    end
    #1;
    if(ode) begin
      if(out !== expected[output_n])
        $fatal(1,"pixel %0d mode %0d got %h expected %h",output_n,mode,out,expected[output_n]);
      output_n=output_n+1;
    end
  end
  task frame;
    begin
      @(negedge clk);vs=1;de=0; repeat(10000) @(negedge clk);vs=0;
      for(j=0;j<8;j=j+1) begin
        for(i=0;i<16;i=i+1) begin @(negedge clk);de=1;rgb=24'hff0000; end
        @(negedge clk);de=0;hs=1;repeat(7) @(negedge clk);hs=0;
      end
      repeat(30) @(negedge clk);
    end
  endtask
  initial begin
    repeat(4) @(negedge clk);reset=0;
    frame();mode=5;frame();mode=0;frame();enable=0;mode=7;frame();
    enable=1;mode=7;frame();mode=6;frame();mode=1;frame();mode=2;frame();frame();mode=3;frame();
    if(output_n!=input_n || output_n!=1280)$fatal(1,"dropped/inserted pixels %0d %0d",input_n,output_n);
    $display("STREAM_PIXELS_PASS pixels=%0d uninterrupted one-pixel-per-clock, gray/binary/raw/disabled",output_n);
    $finish;
  end
  initial begin #2000000;$fatal(1,"timeout");end
endmodule
