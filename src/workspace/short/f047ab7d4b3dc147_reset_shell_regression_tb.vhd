library ieee;
use ieee.std_logic_1164.all;
use std.env.all;

-- The runner audits actual BD constants and compiles its generated wrapper.
entity reset_shell_regression_tb is end entity;
architecture test of reset_shell_regression_tb is
  signal clk : std_logic := '0';
  signal ext_n : std_logic := '0';
  signal rst_n : std_logic_vector(0 downto 0);
begin
  clk <= not clk after 10 ns;
  dut : entity work.filter_candidate_pf_shell_reset_0
    port map(slowest_sync_clk => clk, ext_reset_in => ext_n,
      aux_reset_in => '1', mb_debug_sys_rst => '0', dcm_locked => '1',
      mb_reset => open, bus_struct_reset => open, peripheral_reset => open,
      interconnect_aresetn => open, peripheral_aresetn => rst_n);

  -- UNISIM FDRE models 100 ps clock-to-Q; this is not routed propagation delay.
  edge_check : process(rst_n)
  begin
    if now > 100 ns and rst_n'event then
      assert clk = '1' and clk'last_event <= 100 ps
        report "Peripheral reset changed off rising edge" severity failure;
    end if;
  end process;

  stimulus : process
    procedure await_level(level : std_logic) is
      variable cycles : integer := 0;
    begin
      while rst_n(0) /= level loop
        wait until rising_edge(clk);
        wait for 1 ns;
        cycles := cycles + 1;
        assert cycles < 512 report "Reset transition timeout" severity failure;
      end loop;
    end procedure;
    procedure exercise(low_time : time) is
      variable started : time;
    begin
      -- Assert/deassert off clock edges to exercise input synchronization.
      wait for 6 ns;
      ext_n <= '0';
      await_level('0');
      started := now;
      wait for low_time;
      ext_n <= '1';
      await_level('1');
      assert now-started >= 320 ns
        report "Peripheral reset shorter than 16 clocks" severity failure;
      report "RESET_PULSE_PASS width_ns=" & integer'image(integer((now-started)/1 ns));
      wait for 1000 ns;
      assert rst_n(0) = '1' report "Spurious reset after release" severity failure;
    end procedure;
  begin
    wait for 1001 ns;
    assert rst_n(0) = '0' report "Startup reset not held" severity failure;
    ext_n <= '1';
    await_level('1');
    report "RESET_STARTUP_RELEASE_PASS";
    exercise(401 ns);
    exercise(801 ns);
    exercise(1601 ns);
    report "RESET_REGRESSION_PASS startup=1 repeated=3 synchronous_edges=PASS min_16_cycles=PASS";
    finish;
  end process;
end architecture;
