"""Check the saved reset wiring against the generated vendor wrapper, not defaults."""
import re


def reset_parameters(wrapper):
    keys = ('C_EXT_RESET_HIGH', 'C_AUX_RESET_HIGH', 'C_EXT_RST_WIDTH', 'C_AUX_RST_WIDTH')
    values = {}
    for key in keys:
        match = re.search(r'\b'+key+r"\s*=>\s*'?([0-9]+)'?", wrapper)
        if not match:
            raise ValueError('Generated reset parameter missing: '+key)
        values[key] = int(match[1])
    return values


def reset_failures(design, params):
    failures = []
    nets = [set(n['ports']) for n in design['nets'].values()]

    def same_net(required, label):
        if not any(required <= net for net in nets):
            failures.append('Reset contract: '+label)

    if params != dict(C_EXT_RESET_HIGH=0, C_AUX_RESET_HIGH=0,
                      C_EXT_RST_WIDTH=4, C_AUX_RST_WIDTH=4):
        failures.append('Reset contract: unexpected generated polarity/filter width')
    for name, value in (('pf_shell_one', 1), ('pf_shell_zero', 0)):
        p = design['components'][name]['parameters']
        if int(p['CONST_VAL']['value']) != value or int(p['CONST_WIDTH']['value']) != 1:
            failures.append('Reset contract: constant '+name)
    same_net({'pf_shell_one/dout', 'pf_shell_reset/aux_reset_in',
              'pf_shell_reset/dcm_locked'}, 'aux inactive high / locked high')
    same_net({'pf_shell_zero/dout', 'pf_shell_reset/mb_debug_sys_rst'}, 'debug inactive low')
    same_net({'processing_system7_0/FCLK_RESET0_N', 'pf_shell_reset/ext_reset_in'}, 'PS reset input')
    same_net({'processing_system7_0/FCLK_CLK0', 'pf_shell_reset/slowest_sync_clk',
              'processing_system7_0/M_AXI_GP0_ACLK', 'processing_system7_0/S_AXI_HP0_ACLK',
              'pf_filter/aclk', 'pf_dma/s_axi_lite_aclk', 'pf_dma/m_axi_mm2s_aclk',
              'pf_dma/m_axi_s2mm_aclk', 'pf_control/s_axi_aclk',
              'pf_lite/ACLK', 'pf_lite/S00_ACLK', 'pf_lite/M00_ACLK', 'pf_lite/M01_ACLK',
              'pf_memory/ACLK', 'pf_memory/S00_ACLK', 'pf_memory/S01_ACLK', 'pf_memory/M00_ACLK'},
             'all reset consumers on the same clock')
    same_net({'pf_shell_reset/peripheral_aresetn', 'pf_filter/aresetn',
              'pf_dma/axi_resetn', 'pf_control/s_axi_aresetn', 'pf_lite/ARESETN',
              'pf_lite/S00_ARESETN', 'pf_lite/M00_ARESETN', 'pf_lite/M01_ARESETN',
              'pf_memory/ARESETN', 'pf_memory/S00_ARESETN', 'pf_memory/S01_ARESETN',
              'pf_memory/M00_ARESETN'}, 'shared reset on every AXI side')
    return failures
