`timescale 1ns/1ps
module tb_stream_vectors;
  reg clk=0;always #5 clk=~clk;
  reg reset=1,enable=1,de=0,hs=0,vs=0;reg [3:0] mode=0;
  reg [23:0] rgb=0;wire [23:0] out;wire ode,ohs,ovs;
  reg [23:0] input_words[0:767],golden[0:767];
  integer modes[0:5];integer k,j,i,read_n=0,write_n=0;
  reg [4:0] dpipe=0,hpipe=0,vpipe=0;
  vision_stream_pixels #(.WIDTH(16),.HEIGHT(8)) dut(.clk(clk),.reset(reset),.enable(enable),.mode(mode),
    .in_rgb(rgb),.in_de(de),.in_hsync(hs),.in_vsync(vs),.out_rgb(out),.out_de(ode),.out_hsync(ohs),.out_vsync(ovs));
  always @(posedge clk)begin
    if(reset)begin dpipe=0;hpipe=0;vpipe=0;end
    else begin
      dpipe={dpipe[3:0],de};hpipe={hpipe[3:0],hs};vpipe={vpipe[3:0],vs};
      #1;
      if({ode,ohs,ovs} !== {dpipe[4],hpipe[4],vpipe[4]})$fatal(1,"sync alignment");
      if(ode)begin
        if(out!==golden[read_n])$fatal(1,"vector %0d mode %0d got %h expected %h",read_n,mode,out,golden[read_n]);
        read_n=read_n+1;
      end
    end
  end
  initial begin
    $readmemh("input.hex",input_words);$readmemh("golden.hex",golden);
    modes[0]=0;modes[1]=1;modes[2]=4;modes[3]=5;modes[4]=6;modes[5]=7;
    repeat(4)@(negedge clk);reset=0;
    for(k=0;k<6;k=k+1)begin
      mode=modes[k];vs=1;repeat(10000)@(negedge clk);vs=0;
      for(j=0;j<8;j=j+1)begin
        for(i=0;i<16;i=i+1)begin @(negedge clk);de=1;rgb=input_words[write_n];write_n=write_n+1;end
        @(negedge clk);de=0;hs=1;repeat(9)@(negedge clk);hs=0;
      end
      repeat(30)@(negedge clk);
    end
    if(read_n!=768)$fatal(1,"lost pixels %0d",read_n);
    $display("STREAM_VECTORS_PASS 768 independent pixels, Sobel/median/colour and exact sync latency");$finish;
  end
  initial begin #2000000;$fatal(1,"timeout");end
endmodule
