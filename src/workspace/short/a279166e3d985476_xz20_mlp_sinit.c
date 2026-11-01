// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2023.1 (64-bit)
// Tool Version Limit: 2023.05
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2023 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef __linux__

#include "xstatus.h"
#include "xparameters.h"
#include "xz20_mlp.h"

extern XZ20_mlp_Config XZ20_mlp_ConfigTable[];

XZ20_mlp_Config *XZ20_mlp_LookupConfig(u16 DeviceId) {
	XZ20_mlp_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XZ20_MLP_NUM_INSTANCES; Index++) {
		if (XZ20_mlp_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XZ20_mlp_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XZ20_mlp_Initialize(XZ20_mlp *InstancePtr, u16 DeviceId) {
	XZ20_mlp_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XZ20_mlp_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XZ20_mlp_CfgInitialize(InstancePtr, ConfigPtr);
}

#endif

