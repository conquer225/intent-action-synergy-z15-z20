`timescale 1ns/1ps
module tb_sccb;
 reg clk=0;always #10 clk=~clk;
 reg rst=1,start=0,rd=0;reg [23:0] req=0;wire busy,done,error;wire [7:0] result;wire scl;
 tri1 sda;reg pull=0;assign sda=pull?1'b0:1'bz;
 sccb_master #(.DIV(8)) bus_i(clk,rst,start,rd,req,busy,done,error,result,scl,sda);
 task byte_in(input [7:0] expected,input bit ack);
  integer n;reg [7:0] value;
  begin
   for(n=7;n>=0;n=n-1)begin @(posedge scl);value[n]=sda;end
   if(value!==expected)$fatal(1,"SCCB byte expected %x got %x",expected,value);
   @(negedge scl);pull=ack;@(posedge scl);@(negedge scl);pull=0;
  end
 endtask
 task get_start;begin @(negedge sda);if(!scl)$fatal(1,"bad START");end endtask
 task get_stop;begin @(posedge scl);@(posedge sda);end endtask
 task launch(input bit reading,input [23:0] value);begin @(negedge clk);rd=reading;req=value;start=1;@(negedge clk);start=0;end endtask
 initial begin
  repeat(5)@(negedge clk);rst=0;
  fork
   launch(0,24'h380940);
   begin get_start();byte_in(8'h78,1);byte_in(8'h38,1);byte_in(8'h09,1);byte_in(8'h40,1);get_stop();end
  join
  wait(done);if(error)$fatal(1,"write ACK failed");
  fork
   launch(1,24'h300a00);
   begin
    get_start();byte_in(8'h78,1);byte_in(8'h30,1);byte_in(8'h0a,1);get_stop();
    get_start();byte_in(8'h79,1);
    for(integer n=7;n>=0;n=n-1)begin pull=!(8'h56 & (1<<n));@(posedge scl);@(negedge scl);end
    pull=0;@(posedge scl);if(!sda)$fatal(1,"master must NACK read");@(negedge scl);get_stop();
   end
  join
  wait(done);if(error||result!=8'h56)$fatal(1,"read ID failed %x",result);
  fork launch(0,24'h300802);begin get_start();byte_in(8'h78,0);get_stop();end join
  wait(done);if(!error)$fatal(1,"missing camera not detected");
  $display("PASS tb_sccb: address, register write/read, ACK, NACK");$finish;
 end
 initial begin #2000000;$fatal(1,"SCCB timeout");end
endmodule
