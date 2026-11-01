// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2023.1 (64-bit)
// Tool Version Limit: 2023.05
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2023 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef XZ20_MLP_H
#define XZ20_MLP_H

#ifdef __cplusplus
extern "C" {
#endif

/***************************** Include Files *********************************/
#ifndef __linux__
#include "xil_types.h"
#include "xil_assert.h"
#include "xstatus.h"
#include "xil_io.h"
#else
#include <stdint.h>
#include <assert.h>
#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stddef.h>
#endif
#include "xz20_mlp_hw.h"

/**************************** Type Definitions ******************************/
#ifdef __linux__
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#else
typedef struct {
    u16 DeviceId;
    u64 Control_BaseAddress;
} XZ20_mlp_Config;
#endif

typedef struct {
    u64 Control_BaseAddress;
    u32 IsReady;
} XZ20_mlp;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XZ20_mlp_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XZ20_mlp_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XZ20_mlp_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XZ20_mlp_ReadReg(BaseAddress, RegOffset) \
    *(volatile u32*)((BaseAddress) + (RegOffset))

#define Xil_AssertVoid(expr)    assert(expr)
#define Xil_AssertNonvoid(expr) assert(expr)

#define XST_SUCCESS             0
#define XST_DEVICE_NOT_FOUND    2
#define XST_OPEN_DEVICE_FAILED  3
#define XIL_COMPONENT_IS_READY  1
#endif

/************************** Function Prototypes *****************************/
#ifndef __linux__
int XZ20_mlp_Initialize(XZ20_mlp *InstancePtr, u16 DeviceId);
XZ20_mlp_Config* XZ20_mlp_LookupConfig(u16 DeviceId);
int XZ20_mlp_CfgInitialize(XZ20_mlp *InstancePtr, XZ20_mlp_Config *ConfigPtr);
#else
int XZ20_mlp_Initialize(XZ20_mlp *InstancePtr, const char* InstanceName);
int XZ20_mlp_Release(XZ20_mlp *InstancePtr);
#endif

void XZ20_mlp_Start(XZ20_mlp *InstancePtr);
u32 XZ20_mlp_IsDone(XZ20_mlp *InstancePtr);
u32 XZ20_mlp_IsIdle(XZ20_mlp *InstancePtr);
u32 XZ20_mlp_IsReady(XZ20_mlp *InstancePtr);
void XZ20_mlp_EnableAutoRestart(XZ20_mlp *InstancePtr);
void XZ20_mlp_DisableAutoRestart(XZ20_mlp *InstancePtr);
u32 XZ20_mlp_Get_return(XZ20_mlp *InstancePtr);

void XZ20_mlp_Set_input_r(XZ20_mlp *InstancePtr, u64 Data);
u64 XZ20_mlp_Get_input_r(XZ20_mlp *InstancePtr);
void XZ20_mlp_Set_w1(XZ20_mlp *InstancePtr, u64 Data);
u64 XZ20_mlp_Get_w1(XZ20_mlp *InstancePtr);
void XZ20_mlp_Set_b1(XZ20_mlp *InstancePtr, u64 Data);
u64 XZ20_mlp_Get_b1(XZ20_mlp *InstancePtr);
void XZ20_mlp_Set_w2(XZ20_mlp *InstancePtr, u64 Data);
u64 XZ20_mlp_Get_w2(XZ20_mlp *InstancePtr);
void XZ20_mlp_Set_b2(XZ20_mlp *InstancePtr, u64 Data);
u64 XZ20_mlp_Get_b2(XZ20_mlp *InstancePtr);
void XZ20_mlp_Set_output_r(XZ20_mlp *InstancePtr, u64 Data);
u64 XZ20_mlp_Get_output_r(XZ20_mlp *InstancePtr);
void XZ20_mlp_Set_input_size(XZ20_mlp *InstancePtr, u32 Data);
u32 XZ20_mlp_Get_input_size(XZ20_mlp *InstancePtr);
void XZ20_mlp_Set_hidden_shift(XZ20_mlp *InstancePtr, u32 Data);
u32 XZ20_mlp_Get_hidden_shift(XZ20_mlp *InstancePtr);

void XZ20_mlp_InterruptGlobalEnable(XZ20_mlp *InstancePtr);
void XZ20_mlp_InterruptGlobalDisable(XZ20_mlp *InstancePtr);
void XZ20_mlp_InterruptEnable(XZ20_mlp *InstancePtr, u32 Mask);
void XZ20_mlp_InterruptDisable(XZ20_mlp *InstancePtr, u32 Mask);
void XZ20_mlp_InterruptClear(XZ20_mlp *InstancePtr, u32 Mask);
u32 XZ20_mlp_InterruptGetEnabled(XZ20_mlp *InstancePtr);
u32 XZ20_mlp_InterruptGetStatus(XZ20_mlp *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
