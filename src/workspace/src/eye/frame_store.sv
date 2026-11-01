`timescale 1ns/1ps
module frame_store(input wire clk,rst,input wire word_valid,input wire [27:0] word,
 input wire snapshot_request,snapshot_release,
 output reg snapshot_ready,output wire snapshot_busy,
 input wire [16:0] snapshot_addr,output reg [7:0] snapshot_data,
 input wire pix_clk,input wire [16:0] display_addr,output reg [7:0] display_data);
 (* ram_style="block" *) reg [7:0] preview[0:76799];
 (* ram_style="block" *) reg [7:0] snapshot[0:76799];
 wire [16:0] write_addr=word[16:9]*17'd320+word[25:17];
 reg [1:0] state;
 assign snapshot_busy=state!=0;
 wire pixel=word_valid&&!word[27]&&write_addr<76800;
 always @(posedge clk)begin
  if(pixel)preview[write_addr]<=word[7:0];
  if(pixel&&state==2)snapshot[write_addr]<=word[7:0];
  snapshot_data<=snapshot[snapshot_addr];
  if(rst)begin state<=0;snapshot_ready<=0;end
  else begin
   if(snapshot_release)begin state<=0;snapshot_ready<=0;end
   else case(state)
    0: if(snapshot_request)state<=1;
    1: if(word_valid&&word[27])state<=2;
    2: if(word_valid&&word[27]&&word[26])begin snapshot_ready<=1;state<=3;end
    3: ;
   endcase
  end
 end
 always @(posedge pix_clk)display_data<=preview[display_addr];
endmodule
