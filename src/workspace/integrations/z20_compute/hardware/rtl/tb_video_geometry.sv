`timescale 1ns/1ps
module tb_video_geometry;
 reg clk=0;always #5 clk=~clk;
 reg reset_n=0,awvalid=0,bvalid=0;
 reg [31:0] address=0;reg [7:0] length=0;
 wire [1:0] completed_index[0:1];wire [31:0] sequence_number[0:1],epoch[0:1];
 wire [1:0] fault,valid;
 genvar camera;
 generate for(camera=0;camera<2;camera=camera+1) begin
  z20_video_epoch #(.BASE(32'h01000000+camera*1920)) dut(
   .clk(clk),.reset_n(reset_n),.awvalid(awvalid),.awready(1'b1),
   .awaddr(address+camera*1920),.awlen(length),.awsize(3'd3),
   .bvalid(bvalid),.bready(1'b1),.bresp(2'b00),
   .completed_index(completed_index[camera]),.completed_sequence(sequence_number[camera]),
   .write_epoch(epoch[camera]),.fault(fault[camera]),.completed_valid(valid[camera]));
 end endgenerate
 integer frame,row,burst;
 initial begin
  repeat(3) @(negedge clk);reset_n=1;
  for(frame=0;frame<4;frame=frame+1) begin
   for(row=0;row<720;row=row+1) begin
    for(burst=0;burst<4;burst=burst+1) begin
     @(negedge clk);address='h01000000+(frame%3)*2764800+row*3840+burst*512;
     length=burst==3 ? 47 : 63;awvalid=1;bvalid=0;
     @(negedge clk);awvalid=0;bvalid=1;
     @(negedge clk);bvalid=0;
    end
   end
   repeat(2) @(negedge clk);
   if(fault || valid!=3 || sequence_number[0]!=frame+1 || sequence_number[1]!=frame+1 ||
      completed_index[0]!=frame%3 || completed_index[1]!=frame%3 || epoch[0]!=frame+1 || epoch[1]!=frame+1)
    $fatal(1,"full 640x720 stereo geometry, frame=%d fault=%b sequences=%d/%d",frame,fault,sequence_number[0],sequence_number[1]);
  end
  $display("PASS: four full stereo frames, 512/384-byte bursts, row gaps and triple-buffer wrap");$finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
