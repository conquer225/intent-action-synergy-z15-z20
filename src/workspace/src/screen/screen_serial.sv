`timescale 1ns/1ps
module screen_serial #(parameter REPORT_CYCLES=5000000,UART_DIV=434)(
 input wire clk,rst,rx,output wire tx,
 input wire [1:0] direction,eye_valid,event_direction,
 input wire valid,stale,ready,fault,settled,armed,
 input wire [2:0] mode,calibrated,input wire [4:0] cal_count,
 input wire [3:0] reason,progress,input wire [7:0] ratio0,ratio1,
 input wire [15:0] event_seq,chip_id,
 output reg start,preview,clear,config_changed,
 output reg [50:0] roi0,roi1,output reg [1:0] configured,
 output reg snapshot_request,input wire snapshot_ready,
 output reg snapshot_release,output reg [16:0] snapshot_addr,input wire [7:0] snapshot_data);
 wire [7:0] rx_byte;wire rx_valid,tx_busy;reg tx_start;reg [7:0] tx_byte;
 uart #(.CLKS_PER_BIT(UART_DIV)) uart_i(clk,rst,rx,rx_byte,rx_valid,tx_byte,tx_start,tx_busy,tx);
 reg [3:0] parse;reg [7:0] payload[0:8];reg [7:0] checksum;
 reg [23:0] rx_timeout,report_timer;
 reg [2:0] sending;reg [7:0] char_count;
 reg [1023:0] line_data;reg [16:0] image_count;
 reg ack_pending;reg [111:0] ack_data;
 function automatic [7:0] hex(input [3:0] n);hex=n<10?8'h30+n:8'h41+n-10;endfunction
 function automatic [7:0] dc(input [1:0] n);case(n)1:dc="L";2:dc="C";3:dc="R";default:dc="I";endcase endfunction
 // Exactly 67 bytes including CRLF; padding stays at the LSB end.
 localparam STATUS_LEN=67;
 wire [STATUS_LEN*8-1:0] status_text={"SCR ",dc(direction)," V",hex({3'b0,valid})," F",hex({2'b0,eye_valid}),
  " M",hex({1'b0,mode})," C",hex({1'b0,calibrated})," P",hex({3'b0,cal_count[4]}),hex(cal_count[3:0]),
  " T",hex({3'b0,settled})," H",hex(reason)," G",hex(progress)," A",hex({3'b0,armed}),
  " X",hex(ratio0[7:4]),hex(ratio0[3:0])," Y",hex(ratio1[7:4]),hex(ratio1[3:0]),
  " E",hex(event_seq[15:12]),hex(event_seq[11:8]),hex(event_seq[7:4]),hex(event_seq[3:0]),
  " D",dc(event_direction)," S",hex({3'b0,stale})," I",hex(chip_id[15:12]),hex(chip_id[11:8]),hex(chip_id[7:4]),hex(chip_id[3:0]),
  " R",hex({3'b0,ready})," !",hex({3'b0,fault}),8'h0d,8'h0a};
 wire [15:0] px={payload[1],payload[2]},py={payload[3],payload[4]};
 wire [50:0] other=payload[0]==0?roi1:roi0;
 wire overlap=(px<{6'b0,other[50:41]}+{8'b0,other[31:24]})&&
  (px+{8'b0,payload[5]}>{6'b0,other[50:41]})&&
  (py<{7'b0,other[40:32]}+{8'b0,other[23:16]})&&
  (py+{8'b0,payload[6]}>{7'b0,other[40:32]});
 always @(posedge clk)begin
  start<=0;preview<=0;clear<=0;config_changed<=0;snapshot_request<=0;snapshot_release<=0;tx_start<=0;
  if(rst)begin
   roi0<={10'd224,9'd200,8'd64,8'd32,8'd70,8'd140};roi1<={10'd352,9'd200,8'd64,8'd32,8'd70,8'd140};configured<=0;
   parse<=0;checksum<=0;rx_timeout<=0;report_timer<=0;sending<=0;char_count<=0;
   line_data<=0;image_count<=0;snapshot_addr<=0;tx_byte<=0;ack_pending<=0;ack_data<=0;
  end else begin
   if(report_timer<REPORT_CYCLES)report_timer<=report_timer+1'b1;
   if(parse!=0)begin if(rx_timeout==5000000)parse<=0;else rx_timeout<=rx_timeout+1'b1;end
   if(rx_valid)begin
    rx_timeout<=0;
    if(parse==0)case(rx_byte)
     "a":if(configured==3)start<=1;
     "v":preview<=1;
     "x":clear<=1;
     "p":snapshot_request<=1;
     8'hb5:begin parse<=1;checksum<=0;end
    endcase
    else if(parse<=9)begin payload[parse-1]<=rx_byte;checksum<=checksum^rx_byte;parse<=parse+1'b1;end
    else if(parse==10)begin if(rx_byte==checksum)parse<=11;else parse<=0;end
    else begin
     parse<=0;
     if(rx_byte==8'h5a&&payload[0]<=1&&px<640&&py<480&&payload[5]>=24&&payload[5]<=160&&payload[6]>=12&&payload[6]<=96&&
      px+{8'b0,payload[5]}<=640&&py+{8'b0,payload[6]}<=480&&payload[7]>=8&&
      {1'b0,payload[7]}+16<={1'b0,payload[8]}&&payload[8]<=248&&!ack_pending&&
      !(configured[payload[0]==0?1:0]&&overlap))begin
       if(payload[0]==0)begin roi0<={px[9:0],py[8:0],payload[5],payload[6],payload[7],payload[8]};configured[0]<=1;end
       else begin roi1<={px[9:0],py[8:0],payload[5],payload[6],payload[7],payload[8]};configured[1]<=1;end
       config_changed<=1;ack_pending<=1;
       ack_data<={"RCFG",payload[0],payload[1],payload[2],payload[3],payload[4],payload[5],payload[6],payload[7],payload[8],checksum};
     end
    end
   end
   if(!tx_busy&&!tx_start)case(sending)
    0:if(ack_pending)begin line_data<={ack_data,912'b0};char_count<=14;sending<=1;ack_pending<=0;end
      else if(snapshot_ready)begin line_data<={"ZIMG",8'h40,8'h01,8'hf0,8'h00,960'b0};char_count<=8;sending<=2;snapshot_addr<=0;image_count<=0;end
      else if(report_timer==REPORT_CYCLES)begin line_data<={status_text,{(1024-STATUS_LEN*8){1'b0}}};char_count<=STATUS_LEN;sending<=1;report_timer<=0;end
    1,2:begin
     tx_byte<=line_data[1023:1016];tx_start<=1;line_data<={line_data[1015:0],8'b0};char_count<=char_count-1'b1;
     if(char_count==1)sending<=sending==1?0:3;
    end
    3:begin
     tx_byte<=snapshot_data;tx_start<=1;
     if(image_count==76799)sending<=4;
     else begin image_count<=image_count+1'b1;snapshot_addr<=snapshot_addr+1'b1;end
    end
    4:begin snapshot_release<=1;sending<=5;end
    5:if(!snapshot_ready)sending<=0;
    default:sending<=0;
   endcase
  end
 end
endmodule
