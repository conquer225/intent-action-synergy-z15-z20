`timescale 1ns/1ps
// SPDX-License-Identifier: MIT
// Previous complete-frame histogram drives the current pixel stream. LUT
// construction is confined to vertical blanking; it never stalls video.
module vision_stream_histogram #(parameter WIDTH=1280,HEIGHT=720)(
  input wire clk,reset,enable,de,vs,
  input wire [7:0] gray,
  output reg [7:0] mapped
);
  localparam TOTAL=WIDTH*HEIGHT;
  (* ram_style="block" *) reg [19:0] counts[0:255];
  reg [7:0] lookup[0:255];
  reg [2:0] state;
  reg [7:0] bin,read_address,forward_address;
  reg [19:0] read_count,forward_count,bin_count;
  reg pending,forward_valid,previous_vs,previous_enable,valid,found;
  reg [19:0] pixels,denominator,sum;
  reg [31:0] dividend,quotient;
  reg [32:0] remainder;
  reg [5:0] bits_left;
  reg [7:0] value;
  wire [19:0] next_count=(forward_valid && read_address==forward_address?forward_count:read_count)+1'b1;
  wire [32:0] trial={remainder[31:0],dividend[31]};
  wire subtract=trial>={13'd0,denominator};
  wire [31:0] next_quotient={quotient[30:0],subtract};
  always @(posedge clk)begin
    if(reset)begin
      state<=1;bin<=0;pending<=0;forward_valid<=0;previous_vs<=0;
      previous_enable<=0;valid<=0;pixels<=0;found<=0;mapped<=0;
    end else begin
      previous_vs<=vs;previous_enable<=enable;
      mapped<=enable && valid?lookup[gray]:gray;
      if(enable!=previous_enable)begin
        state<=1;bin<=0;valid<=0;pixels<=0;pending<=0;forward_valid<=0;
      end else case(state)
        0:begin
          pending<=de && enable;
          if(de && enable)begin read_count<=counts[gray];read_address<=gray;pixels<=pixels+1'b1;end
          if(pending)begin
            counts[read_address]<=next_count;forward_count<=next_count;
            forward_address<=read_address;forward_valid<=1;
          end
          if(vs && !previous_vs && enable)begin
            pending<=0;forward_valid<=0;bin<=0;sum<=0;found<=0;
            if(pixels==TOTAL)state<=2;
            else begin state<=1;valid<=0;end
            pixels<=0;
          end
        end
        1:begin counts[bin]<=0;if(bin==255)state<=0;else bin<=bin+1'b1;end
        2:begin bin_count<=counts[bin];counts[bin]<=0;state<=3;end
        3:begin
          if(!found)begin
            value<=0;state<=5;
            if(bin_count!=0)begin found<=1;denominator<=TOTAL-bin_count;if(bin_count==TOTAL)value<=bin;end
          end else if(denominator==0)begin value<=bin;state<=5;end
          else begin
            sum<=sum+bin_count;dividend<=(sum+bin_count)*255;
            quotient<=0;remainder<=0;bits_left<=32;state<=4;
          end
        end
        4:begin
          remainder<=subtract?trial-{13'd0,denominator}:trial;
          dividend<={dividend[30:0],1'b0};quotient<=next_quotient;bits_left<=bits_left-1'b1;
          if(bits_left==1)begin value<=next_quotient[7:0];state<=5;end
        end
        5:begin
          lookup[bin]<=value;
          if(bin==255)begin valid<=1;state<=0;end else begin bin<=bin+1'b1;state<=2;end
        end
        default:state<=1;
      endcase
    end
  end
endmodule
