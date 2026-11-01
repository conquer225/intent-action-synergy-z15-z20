//****************************************Copyright (c)***********************************//
//原子哥在线教学平台：www.yuanzige.com
//技术支持：http://www.openedv.com/forum.php
//淘宝店铺：https://zhengdianyuanzi.tmall.com
//关注微信公众平台微信号："正点原子"，免费获取ZYNQ & FPGA & STM32 & LINUX资料。
//版权所有，盗版必究。
//Copyright(C) 正点原子 2023-2033
//All rights reserved                                  
//----------------------------------------------------------------------------------------
// File name:           key_led
// Created by:          正点原子
// Created date:        2023年2月10日14:17:02
// Version:             V1.0
// Descriptions:        按键控制LED实验
//
//----------------------------------------------------------------------------------------
//****************************************************************************************//

module key_led(
    input               sys_clk   ,  //系统时钟
    input               sys_rst_n ,  //系统复位，低电平有效

    input        [1:0]  key       ,  //按键
    output  reg  [1:0]  led          //LED灯
);

//parameter define
parameter  CNT_MAX = 25'd2500_0000;    //LED灯闪烁频率

//reg define
reg [24:0] cnt;                      //计数器
reg        led_flag;                 //LED控制信号

//*****************************************************
//**                    main code
//*****************************************************

//计数器计时0.5s
always @(posedge sys_clk or negedge sys_rst_n) begin
    if(!sys_rst_n)
        cnt <= 25'd0;
    else if(cnt < (CNT_MAX - 25'd1))
        cnt <= cnt + 25'd1;
    else
        cnt <= 25'd0;
end

//每隔500ms就更改LED的闪烁状态
always @ (posedge sys_clk or negedge sys_rst_n) begin
    if(!sys_rst_n)
        led_flag <= 1'b0;
    else if(cnt == (CNT_MAX - 25'd1))
        led_flag <= ~led_flag;
end

//根据按键的状态以及LED的闪烁状态来赋值LED
always @ (posedge sys_clk or negedge sys_rst_n) begin
    if(!sys_rst_n)
        led <= 2'b00;
    else case(key)
        2'b10 :  //如果按键0被按下，则两个LED交替闪烁
            if(led_flag == 1'b0)
                led <= 2'b01;
            else
                led <= 2'b10;
        2'b01 :  //如果按键1被按下，则两个LED同时亮灭交替
            if(led_flag == 1'b0)
                led <= 2'b11;
            else
                led <= 2'b00;
        2'b11 :  //如果两个按键都未被按下，则两个LED都保持长灭
                led <= 2'b00;
        default: ;
    endcase
end

endmodule
