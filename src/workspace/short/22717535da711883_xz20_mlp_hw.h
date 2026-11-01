// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2023.1 (64-bit)
// Tool Version Limit: 2023.05
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2023 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
// control
// 0x00 : Control signals
//        bit 0  - ap_start (Read/Write/COH)
//        bit 1  - ap_done (Read/COR)
//        bit 2  - ap_idle (Read)
//        bit 3  - ap_ready (Read/COR)
//        bit 7  - auto_restart (Read/Write)
//        bit 9  - interrupt (Read)
//        others - reserved
// 0x04 : Global Interrupt Enable Register
//        bit 0  - Global Interrupt Enable (Read/Write)
//        others - reserved
// 0x08 : IP Interrupt Enable Register (Read/Write)
//        bit 0 - enable ap_done interrupt (Read/Write)
//        bit 1 - enable ap_ready interrupt (Read/Write)
//        others - reserved
// 0x0c : IP Interrupt Status Register (Read/TOW)
//        bit 0 - ap_done (Read/TOW)
//        bit 1 - ap_ready (Read/TOW)
//        others - reserved
// 0x10 : Data signal of ap_return
//        bit 31~0 - ap_return[31:0] (Read)
// 0x18 : Data signal of input_r
//        bit 31~0 - input_r[31:0] (Read/Write)
// 0x1c : Data signal of input_r
//        bit 31~0 - input_r[63:32] (Read/Write)
// 0x20 : reserved
// 0x24 : Data signal of w1
//        bit 31~0 - w1[31:0] (Read/Write)
// 0x28 : Data signal of w1
//        bit 31~0 - w1[63:32] (Read/Write)
// 0x2c : reserved
// 0x30 : Data signal of b1
//        bit 31~0 - b1[31:0] (Read/Write)
// 0x34 : Data signal of b1
//        bit 31~0 - b1[63:32] (Read/Write)
// 0x38 : reserved
// 0x3c : Data signal of w2
//        bit 31~0 - w2[31:0] (Read/Write)
// 0x40 : Data signal of w2
//        bit 31~0 - w2[63:32] (Read/Write)
// 0x44 : reserved
// 0x48 : Data signal of b2
//        bit 31~0 - b2[31:0] (Read/Write)
// 0x4c : Data signal of b2
//        bit 31~0 - b2[63:32] (Read/Write)
// 0x50 : reserved
// 0x54 : Data signal of output_r
//        bit 31~0 - output_r[31:0] (Read/Write)
// 0x58 : Data signal of output_r
//        bit 31~0 - output_r[63:32] (Read/Write)
// 0x5c : reserved
// 0x60 : Data signal of input_size
//        bit 31~0 - input_size[31:0] (Read/Write)
// 0x64 : reserved
// 0x68 : Data signal of hidden_shift
//        bit 31~0 - hidden_shift[31:0] (Read/Write)
// 0x6c : reserved
// (SC = Self Clear, COR = Clear on Read, TOW = Toggle on Write, COH = Clear on Handshake)

#define XZ20_MLP_CONTROL_ADDR_AP_CTRL           0x00
#define XZ20_MLP_CONTROL_ADDR_GIE               0x04
#define XZ20_MLP_CONTROL_ADDR_IER               0x08
#define XZ20_MLP_CONTROL_ADDR_ISR               0x0c
#define XZ20_MLP_CONTROL_ADDR_AP_RETURN         0x10
#define XZ20_MLP_CONTROL_BITS_AP_RETURN         32
#define XZ20_MLP_CONTROL_ADDR_INPUT_R_DATA      0x18
#define XZ20_MLP_CONTROL_BITS_INPUT_R_DATA      64
#define XZ20_MLP_CONTROL_ADDR_W1_DATA           0x24
#define XZ20_MLP_CONTROL_BITS_W1_DATA           64
#define XZ20_MLP_CONTROL_ADDR_B1_DATA           0x30
#define XZ20_MLP_CONTROL_BITS_B1_DATA           64
#define XZ20_MLP_CONTROL_ADDR_W2_DATA           0x3c
#define XZ20_MLP_CONTROL_BITS_W2_DATA           64
#define XZ20_MLP_CONTROL_ADDR_B2_DATA           0x48
#define XZ20_MLP_CONTROL_BITS_B2_DATA           64
#define XZ20_MLP_CONTROL_ADDR_OUTPUT_R_DATA     0x54
#define XZ20_MLP_CONTROL_BITS_OUTPUT_R_DATA     64
#define XZ20_MLP_CONTROL_ADDR_INPUT_SIZE_DATA   0x60
#define XZ20_MLP_CONTROL_BITS_INPUT_SIZE_DATA   32
#define XZ20_MLP_CONTROL_ADDR_HIDDEN_SHIFT_DATA 0x68
#define XZ20_MLP_CONTROL_BITS_HIDDEN_SHIFT_DATA 32

