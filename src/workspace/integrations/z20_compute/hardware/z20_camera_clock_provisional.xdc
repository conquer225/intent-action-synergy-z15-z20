# Provisional routing exceptions, separate from the pin provenance constraints.
# Official Z20 experiment 37 pin.xdc lines 4/7 applies these same two nets.
# 2023.1 placement reports Place 30-876 for cam_pclk_1 on C20 (clock N pin).
# This permits fabric routing; it does not specify camera input delays or
# establish measured DVP timing margin. Keep these exceptions in board review.
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets cam_pclk_0_IBUF]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets cam_pclk_1_IBUF]
