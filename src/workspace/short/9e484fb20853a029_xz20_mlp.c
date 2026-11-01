// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2023.1 (64-bit)
// Tool Version Limit: 2023.05
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2023 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
/***************************** Include Files *********************************/
#include "xz20_mlp.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XZ20_mlp_CfgInitialize(XZ20_mlp *InstancePtr, XZ20_mlp_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Control_BaseAddress = ConfigPtr->Control_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XZ20_mlp_Start(XZ20_mlp *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_AP_CTRL) & 0x80;
    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XZ20_mlp_IsDone(XZ20_mlp *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XZ20_mlp_IsIdle(XZ20_mlp *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XZ20_mlp_IsReady(XZ20_mlp *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XZ20_mlp_EnableAutoRestart(XZ20_mlp *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_AP_CTRL, 0x80);
}

void XZ20_mlp_DisableAutoRestart(XZ20_mlp *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_AP_CTRL, 0);
}

u32 XZ20_mlp_Get_return(XZ20_mlp *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_AP_RETURN);
    return Data;
}
void XZ20_mlp_Set_input_r(XZ20_mlp *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_INPUT_R_DATA, (u32)(Data));
    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_INPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XZ20_mlp_Get_input_r(XZ20_mlp *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_INPUT_R_DATA);
    Data += (u64)XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_INPUT_R_DATA + 4) << 32;
    return Data;
}

void XZ20_mlp_Set_w1(XZ20_mlp *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_W1_DATA, (u32)(Data));
    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_W1_DATA + 4, (u32)(Data >> 32));
}

u64 XZ20_mlp_Get_w1(XZ20_mlp *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_W1_DATA);
    Data += (u64)XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_W1_DATA + 4) << 32;
    return Data;
}

void XZ20_mlp_Set_b1(XZ20_mlp *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_B1_DATA, (u32)(Data));
    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_B1_DATA + 4, (u32)(Data >> 32));
}

u64 XZ20_mlp_Get_b1(XZ20_mlp *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_B1_DATA);
    Data += (u64)XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_B1_DATA + 4) << 32;
    return Data;
}

void XZ20_mlp_Set_w2(XZ20_mlp *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_W2_DATA, (u32)(Data));
    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_W2_DATA + 4, (u32)(Data >> 32));
}

u64 XZ20_mlp_Get_w2(XZ20_mlp *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_W2_DATA);
    Data += (u64)XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_W2_DATA + 4) << 32;
    return Data;
}

void XZ20_mlp_Set_b2(XZ20_mlp *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_B2_DATA, (u32)(Data));
    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_B2_DATA + 4, (u32)(Data >> 32));
}

u64 XZ20_mlp_Get_b2(XZ20_mlp *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_B2_DATA);
    Data += (u64)XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_B2_DATA + 4) << 32;
    return Data;
}

void XZ20_mlp_Set_output_r(XZ20_mlp *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_OUTPUT_R_DATA, (u32)(Data));
    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_OUTPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XZ20_mlp_Get_output_r(XZ20_mlp *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_OUTPUT_R_DATA);
    Data += (u64)XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_OUTPUT_R_DATA + 4) << 32;
    return Data;
}

void XZ20_mlp_Set_input_size(XZ20_mlp *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_INPUT_SIZE_DATA, Data);
}

u32 XZ20_mlp_Get_input_size(XZ20_mlp *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_INPUT_SIZE_DATA);
    return Data;
}

void XZ20_mlp_Set_hidden_shift(XZ20_mlp *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_HIDDEN_SHIFT_DATA, Data);
}

u32 XZ20_mlp_Get_hidden_shift(XZ20_mlp *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_HIDDEN_SHIFT_DATA);
    return Data;
}

void XZ20_mlp_InterruptGlobalEnable(XZ20_mlp *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_GIE, 1);
}

void XZ20_mlp_InterruptGlobalDisable(XZ20_mlp *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_GIE, 0);
}

void XZ20_mlp_InterruptEnable(XZ20_mlp *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_IER);
    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_IER, Register | Mask);
}

void XZ20_mlp_InterruptDisable(XZ20_mlp *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_IER);
    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_IER, Register & (~Mask));
}

void XZ20_mlp_InterruptClear(XZ20_mlp *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZ20_mlp_WriteReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_ISR, Mask);
}

u32 XZ20_mlp_InterruptGetEnabled(XZ20_mlp *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_IER);
}

u32 XZ20_mlp_InterruptGetStatus(XZ20_mlp *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XZ20_mlp_ReadReg(InstancePtr->Control_BaseAddress, XZ20_MLP_CONTROL_ADDR_ISR);
}

