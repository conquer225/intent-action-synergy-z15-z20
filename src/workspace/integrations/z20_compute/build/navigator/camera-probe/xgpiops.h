#include "xil_types.h"
#define XPAR_XGPIOPS_0_DEVICE_ID 0
typedef struct {unsigned BaseAddr;} XGpioPs_Config;
typedef struct {int unused;} XGpioPs;
XGpioPs_Config *XGpioPs_LookupConfig(unsigned);
int XGpioPs_CfgInitialize(XGpioPs *,XGpioPs_Config *,unsigned);
void XGpioPs_SetDirectionPin(XGpioPs *,unsigned,unsigned);
void XGpioPs_SetOutputEnablePin(XGpioPs *,unsigned,unsigned);
void XGpioPs_WritePin(XGpioPs *,unsigned,unsigned);
unsigned XGpioPs_ReadPin(XGpioPs *,unsigned);
