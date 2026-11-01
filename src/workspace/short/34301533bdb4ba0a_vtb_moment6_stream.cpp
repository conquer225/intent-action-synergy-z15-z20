// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Model implementation (design independent parts)

#include "Vtb_moment6_stream.h"
#include "Vtb_moment6_stream__Syms.h"

//============================================================
// Constructors

Vtb_moment6_stream::Vtb_moment6_stream(VerilatedContext* _vcontextp__, const char* _vcname__)
    : VerilatedModel{*_vcontextp__}
    , vlSymsp{new Vtb_moment6_stream__Syms(contextp(), _vcname__, this)}
    , rootp{&(vlSymsp->TOP)}
{
    // Register model with the context
    contextp()->addModel(this);
}

Vtb_moment6_stream::Vtb_moment6_stream(const char* _vcname__)
    : Vtb_moment6_stream(Verilated::threadContextp(), _vcname__)
{
}

//============================================================
// Destructor

Vtb_moment6_stream::~Vtb_moment6_stream() {
    delete vlSymsp;
}

//============================================================
// Evaluation function

#ifdef VL_DEBUG
void Vtb_moment6_stream___024root___eval_debug_assertions(Vtb_moment6_stream___024root* vlSelf);
#endif  // VL_DEBUG
void Vtb_moment6_stream___024root___eval_static(Vtb_moment6_stream___024root* vlSelf);
void Vtb_moment6_stream___024root___eval_initial(Vtb_moment6_stream___024root* vlSelf);
void Vtb_moment6_stream___024root___eval_settle(Vtb_moment6_stream___024root* vlSelf);
void Vtb_moment6_stream___024root___eval(Vtb_moment6_stream___024root* vlSelf);

void Vtb_moment6_stream::eval_step() {
    VL_DEBUG_IF(VL_DBG_MSGF("+++++TOP Evaluate Vtb_moment6_stream::eval_step\n"); );
#ifdef VL_DEBUG
    // Debug assertions
    Vtb_moment6_stream___024root___eval_debug_assertions(&(vlSymsp->TOP));
#endif  // VL_DEBUG
    if (VL_UNLIKELY(!vlSymsp->__Vm_didInit)) {
        vlSymsp->__Vm_didInit = true;
        VL_DEBUG_IF(VL_DBG_MSGF("+ Initial\n"););
        Vtb_moment6_stream___024root___eval_static(&(vlSymsp->TOP));
        Vtb_moment6_stream___024root___eval_initial(&(vlSymsp->TOP));
        Vtb_moment6_stream___024root___eval_settle(&(vlSymsp->TOP));
    }
    // MTask 0 start
    VL_DEBUG_IF(VL_DBG_MSGF("MTask0 starting\n"););
    Verilated::mtaskId(0);
    VL_DEBUG_IF(VL_DBG_MSGF("+ Eval\n"););
    Vtb_moment6_stream___024root___eval(&(vlSymsp->TOP));
    // Evaluate cleanup
    Verilated::endOfThreadMTask(vlSymsp->__Vm_evalMsgQp);
    Verilated::endOfEval(vlSymsp->__Vm_evalMsgQp);
}

//============================================================
// Events and timing
bool Vtb_moment6_stream::eventsPending() { return !vlSymsp->TOP.__VdlySched.empty(); }

uint64_t Vtb_moment6_stream::nextTimeSlot() { return vlSymsp->TOP.__VdlySched.nextTimeSlot(); }

//============================================================
// Utilities

const char* Vtb_moment6_stream::name() const {
    return vlSymsp->name();
}

//============================================================
// Invoke final blocks

void Vtb_moment6_stream___024root___eval_final(Vtb_moment6_stream___024root* vlSelf);

VL_ATTR_COLD void Vtb_moment6_stream::final() {
    Vtb_moment6_stream___024root___eval_final(&(vlSymsp->TOP));
}

//============================================================
// Implementations of abstract methods from VerilatedModel

const char* Vtb_moment6_stream::hierName() const { return vlSymsp->name(); }
const char* Vtb_moment6_stream::modelName() const { return "Vtb_moment6_stream"; }
unsigned Vtb_moment6_stream::threads() const { return 1; }
