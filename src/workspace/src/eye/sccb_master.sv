`timescale 1ns/1ps
// 100 kHz SCCB, 16-bit register address. Open-drain SDA; SCL push-pull.
// Read uses register-address write, STOP, then read transaction (OV5640 SCCB).
module sccb_master #(parameter DIV=125)(
 input wire clk,rst,start,rd,input wire [23:0] request,
 output reg busy,done,error, output reg [7:0] result,
 output reg scl, inout wire sda);
 reg drive_low; assign sda=drive_low?1'b0:1'bz;
 (* ASYNC_REG="TRUE" *) reg [1:0] sd;
 reg [15:0] timer;
 reg [3:0] state;
 reg [1:0] phase,byte_no;
 reg [3:0] bit_no;
 reg [7:0] shift;
 reg [23:0] saved;
 reg reading,read_phase;
 localparam IDLE=0,START=1,BITS=2,ACK=3,STOP=4,RECV=5,NACK=6;
 always @(posedge clk) begin
  sd<={sd[0],sda}; done<=0;
  if(rst) begin state<=IDLE; scl<=1;drive_low<=0;busy<=0;error<=0;timer<=0;phase<=0;result<=0;end
  else if(state==IDLE) begin
   if(start) begin saved<=request;reading<=rd;read_phase<=0;busy<=1;error<=0;timer<=0;phase<=0;state<=START;end
  end else if(timer==DIV-1) begin
   timer<=0;phase<=phase+1'b1;
   case(state)
    START: case(phase)
     0: begin scl<=1;drive_low<=0;end
     1: begin drive_low<=1; if(!sd[1])error<=1;end
     2: scl<=0;
     3: begin shift<=read_phase?8'h79:8'h78;bit_no<=7;byte_no<=0;state<=BITS;end
    endcase
    BITS: case(phase)
     0: drive_low<=!shift[bit_no];
     1: scl<=1;
     2: ;
     3: begin scl<=0;if(bit_no==0)state<=ACK;else bit_no<=bit_no-1'b1;end
    endcase
    ACK: case(phase)
     0: drive_low<=0;
     1: scl<=1;
     2: if(sd[1])error<=1;
     3: begin
      scl<=0;bit_no<=7;
      if(error)state<=STOP;
      else if(read_phase)begin state<=RECV;shift<=0;end
      else if(byte_no==(reading?2:3))state<=STOP;
      else begin byte_no<=byte_no+1'b1;state<=BITS;
       case(byte_no)0:shift<=saved[23:16];1:shift<=saved[15:8];2:shift<=saved[7:0];default:shift<=0;endcase
      end
     end
    endcase
    RECV: case(phase)
     0: drive_low<=0;
     1: scl<=1;
     2: shift[bit_no]<=sd[1];
     3: begin scl<=0;if(bit_no==0)begin result<=shift;state<=NACK;end else bit_no<=bit_no-1'b1;end
    endcase
    NACK: case(phase)0:drive_low<=0;1:scl<=1;2:;3:begin scl<=0;state<=STOP;end endcase
    STOP: case(phase)
     0: drive_low<=1;
     1: scl<=1;
     2: drive_low<=0;
     3: if(reading&&!read_phase&&!error)begin read_phase<=1;state<=START;end
        else begin state<=IDLE;busy<=0;done<=1;end
    endcase
   endcase
  end else timer<=timer+1'b1;
 end
endmodule
