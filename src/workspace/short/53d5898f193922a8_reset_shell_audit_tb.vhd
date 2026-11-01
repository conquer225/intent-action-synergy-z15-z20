library ieee;
use ieee.std_logic_1164.all;
library proc_sys_reset_v5_0_17;
use std.env.all;

-- Vendor-IP diagnostic only. Case 0 reproduces the generated candidate;
-- case 1 is a simulation control, not a change to the candidate design.
entity reset_shell_audit_tb is end entity;
architecture test of reset_shell_audit_tb is
  signal clk : std_logic := '0';
  signal ext_resetn : std_logic := '0';
  signal aux_resetn : std_logic_vector(1 downto 0) := "10";
  signal resetn : std_logic_vector(1 downto 0);
begin
  clk <= not clk after 10 ns;
  cases : for i in 0 to 1 generate
    dut : entity proc_sys_reset_v5_0_17.proc_sys_reset
      generic map(C_FAMILY => "zynq", C_EXT_RST_WIDTH => 4,
        C_AUX_RST_WIDTH => 4, C_EXT_RESET_HIGH => '0',
        C_AUX_RESET_HIGH => '0', C_NUM_BUS_RST => 1, C_NUM_PERP_RST => 1,
        C_NUM_INTERCONNECT_ARESETN => 1, C_NUM_PERP_ARESETN => 1)
      port map(slowest_sync_clk => clk, ext_reset_in => ext_resetn,
        aux_reset_in => aux_resetn(i), mb_debug_sys_rst => '0',
        dcm_locked => '1', mb_reset => open, bus_struct_reset => open,
        peripheral_reset => open, interconnect_aresetn => open,
        peripheral_aresetn(0) => resetn(i));
  end generate;
  stimulus : process
  begin
    wait for 1000 ns;
    ext_resetn <= '1';
    wait for 20000 ns;
    assert resetn(0) = '0' report "Expected candidate held in reset" severity failure;
    assert resetn(1) = '1' report "Control failed to release reset" severity failure;
    report "RESET_DIAGNOSIS_CONFIRMED: aux_low_active_tied_zero=held; inactive_aux_control=released";
    -- Release the offending auxiliary input only in this diagnostic simulation.
    aux_resetn(0) <= '1';
    wait for 20000 ns;
    assert resetn = "11" report "Diagnostic auxiliary release failed" severity failure;
    report "RESET_AUDIT_PASS: vendor_IP_reproduces_persistent_reset_and_release";
    finish;
  end process;
end architecture;
