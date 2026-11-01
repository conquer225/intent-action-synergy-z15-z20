set_property -dict {PACKAGE_PIN H5 IOSTANDARD LVCMOS18} [get_ports {pl_keys[0]}]
set_property -dict {PACKAGE_PIN H6 IOSTANDARD LVCMOS18} [get_ports {pl_keys[1]}]
# Asynchronous physical button inputs terminate at the first synchronizer stage.
set key_first [get_pins -of_objects [get_cells -hier -regexp {.*key_inputs_0/inst/meta_reg.*}] -filter {REF_PIN_NAME == D}]
set_false_path -from [get_ports pl_keys*] -to $key_first
