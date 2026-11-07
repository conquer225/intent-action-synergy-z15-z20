
################################################################
# This is a generated script based on design: system
#
# Though there are limitations about the generated script,
# the main purpose of this utility is to make learning
# IP Integrator Tcl commands easier.
################################################################

namespace eval _tcl {
proc get_script_folder {} {
   set script_path [file normalize [info script]]
   set script_folder [file dirname $script_path]
   return $script_folder
}
}
variable script_folder
set script_folder [_tcl::get_script_folder]

################################################################
# Check if script is running in correct Vivado version.
################################################################
set scripts_vivado_version 2023.1
set current_vivado_version [version -short]

if { [string first $scripts_vivado_version $current_vivado_version] == -1 } {
   puts ""
   catch {common::send_gid_msg -ssname BD::TCL -id 2041 -severity "ERROR" "This script was generated using Vivado <$scripts_vivado_version> and is being run in <$current_vivado_version> of Vivado. Please run the script in Vivado <$scripts_vivado_version> then open the design in Vivado <$current_vivado_version>. Upgrade the design by running \"Tools => Report => Report IP Status...\", then run write_bd_tcl to create an updated script."}

   return 1
}

################################################################
# START
################################################################

# To test this script, run the following commands from Vivado Tcl console:
# source system_script.tcl


# The design that will be created by this Tcl script contains the following 
# module references:
# display_status, hdmi_audio_tx, audio_sample_tick, pcm_buffer, vision_stream_control, key_inputs

# Please add the sources of those modules before sourcing this Tcl script.

# If there is no project opened, this script will create a
# project, but make sure you do not have an existing project
# <./myproj/project_1.xpr> in the current working folder.

set list_projs [get_projects -quiet]
if { $list_projs eq "" } {
   create_project project_1 myproj -part xc7z015clg485-2
}


# CHANGE DESIGN NAME HERE
variable design_name
set design_name system

# If you do not already have an existing IP Integrator design open,
# you can create a design using the following command:
#    create_bd_design $design_name

# Creating design if needed
set errMsg ""
set nRet 0

set cur_design [current_bd_design -quiet]
set list_cells [get_bd_cells -quiet]

if { ${design_name} eq "" } {
   # USE CASES:
   #    1) Design_name not set

   set errMsg "Please set the variable <design_name> to a non-empty value."
   set nRet 1

} elseif { ${cur_design} ne "" && ${list_cells} eq "" } {
   # USE CASES:
   #    2): Current design opened AND is empty AND names same.
   #    3): Current design opened AND is empty AND names diff; design_name NOT in project.
   #    4): Current design opened AND is empty AND names diff; design_name exists in project.

   if { $cur_design ne $design_name } {
      common::send_gid_msg -ssname BD::TCL -id 2001 -severity "INFO" "Changing value of <design_name> from <$design_name> to <$cur_design> since current design is empty."
      set design_name [get_property NAME $cur_design]
   }
   common::send_gid_msg -ssname BD::TCL -id 2002 -severity "INFO" "Constructing design in IPI design <$cur_design>..."

} elseif { ${cur_design} ne "" && $list_cells ne "" && $cur_design eq $design_name } {
   # USE CASES:
   #    5) Current design opened AND has components AND same names.

   set errMsg "Design <$design_name> already exists in your project, please set the variable <design_name> to another value."
   set nRet 1
} elseif { [get_files -quiet ${design_name}.bd] ne "" } {
   # USE CASES: 
   #    6) Current opened design, has components, but diff names, design_name exists in project.
   #    7) No opened design, design_name exists in project.

   set errMsg "Design <$design_name> already exists in your project, please set the variable <design_name> to another value."
   set nRet 2

} else {
   # USE CASES:
   #    8) No opened design, design_name not in project.
   #    9) Current opened design, has components, but diff names, design_name not in project.

   common::send_gid_msg -ssname BD::TCL -id 2003 -severity "INFO" "Currently there is no design <$design_name> in project, so creating one..."

   create_bd_design $design_name

   common::send_gid_msg -ssname BD::TCL -id 2004 -severity "INFO" "Making design <$design_name> as current_bd_design."
   current_bd_design $design_name

}

common::send_gid_msg -ssname BD::TCL -id 2005 -severity "INFO" "Currently the variable <design_name> is equal to \"$design_name\"."

if { $nRet != 0 } {
   catch {common::send_gid_msg -ssname BD::TCL -id 2006 -severity "ERROR" $errMsg}
   return $nRet
}

set bCheckIPsPassed 1
##################################################################
# CHECK IPs
##################################################################
set bCheckIPs 1
if { $bCheckIPs == 1 } {
   set list_check_ips "\ 
xilinx.com:ip:axi_vdma:6.3\
xilinx.com:ip:clk_wiz:6.0\
alientek.com:user:ov5640_capture_data:1.0\
xilinx.com:ip:processing_system7:5.5\
xilinx.com:ip:proc_sys_reset:5.0\
xilinx.com:ip:util_vector_logic:2.0\
xilinx.com:ip:v_axi4s_vid_out:4.0\
xilinx.com:ip:v_tc:6.2\
xilinx.com:ip:v_vid_in_axi4s:5.0\
xilinx.com:ip:axi_gpio:2.0\
xilinx.com:hls:audio_fft:1.0\
xilinx.com:hls:z15_fbcsp:1.0\
xilinx.com:ip:xlconstant:1.1\
"

   set list_ips_missing ""
   common::send_gid_msg -ssname BD::TCL -id 2011 -severity "INFO" "Checking if the following IPs exist in the project's IP catalog: $list_check_ips ."

   foreach ip_vlnv $list_check_ips {
      set ip_obj [get_ipdefs -all $ip_vlnv]
      if { $ip_obj eq "" } {
         lappend list_ips_missing $ip_vlnv
      }
   }

   if { $list_ips_missing ne "" } {
      catch {common::send_gid_msg -ssname BD::TCL -id 2012 -severity "ERROR" "The following IPs are not found in the IP Catalog:\n  $list_ips_missing\n\nResolution: Please add the repository containing the IP(s) to the project." }
      set bCheckIPsPassed 0
   }

}

##################################################################
# CHECK Modules
##################################################################
set bCheckModules 1
if { $bCheckModules == 1 } {
   set list_check_mods "\ 
display_status\
hdmi_audio_tx\
audio_sample_tick\
pcm_buffer\
vision_stream_control\
key_inputs\
"

   set list_mods_missing ""
   common::send_gid_msg -ssname BD::TCL -id 2020 -severity "INFO" "Checking if the following modules exist in the project's sources: $list_check_mods ."

   foreach mod_vlnv $list_check_mods {
      if { [can_resolve_reference $mod_vlnv] == 0 } {
         lappend list_mods_missing $mod_vlnv
      }
   }

   if { $list_mods_missing ne "" } {
      catch {common::send_gid_msg -ssname BD::TCL -id 2021 -severity "ERROR" "The following module(s) are not found in the project: $list_mods_missing" }
      common::send_gid_msg -ssname BD::TCL -id 2022 -severity "INFO" "Please add source files for the missing module(s) above."
      set bCheckIPsPassed 0
   }
}

if { $bCheckIPsPassed != 1 } {
  common::send_gid_msg -ssname BD::TCL -id 2023 -severity "WARNING" "Will not continue with creation of design due to the error(s) above."
  return 3
}

##################################################################
# DESIGN PROCs
##################################################################



# Procedure to create entire design; Provide argument to make
# procedure reusable. If parentCell is "", will use root.
proc create_root_design { parentCell } {

  variable script_folder
  variable design_name

  if { $parentCell eq "" } {
     set parentCell [get_bd_cells /]
  }

  # Get object for parentCell
  set parentObj [get_bd_cells $parentCell]
  if { $parentObj == "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2090 -severity "ERROR" "Unable to find parent cell <$parentCell>!"}
     return
  }

  # Make sure parentObj is hier blk
  set parentType [get_property TYPE $parentObj]
  if { $parentType ne "hier" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2091 -severity "ERROR" "Parent <$parentObj> has TYPE = <$parentType>. Expected to be <hier>."}
     return
  }

  # Save current instance; Restore later
  set oldCurInst [current_bd_instance .]

  # Set parent object as current
  current_bd_instance $parentObj


  # Create interface ports
  set emio_sccb [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:gpio_rtl:1.0 emio_sccb ]

  set DDR [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:ddrx_rtl:1.0 DDR ]

  set FIXED_IO [ create_bd_intf_port -mode Master -vlnv xilinx.com:display_processing_system7:fixedio_rtl:1.0 FIXED_IO ]


  # Create ports
  set TMDS_0_tmds_data_p [ create_bd_port -dir O -from 2 -to 0 TMDS_0_tmds_data_p ]
  set TMDS_0_tmds_clk_p [ create_bd_port -dir O TMDS_0_tmds_clk_p ]
  set TMDS_0_tmds_data_n [ create_bd_port -dir O -from 2 -to 0 TMDS_0_tmds_data_n ]
  set TMDS_0_tmds_clk_n [ create_bd_port -dir O TMDS_0_tmds_clk_n ]
  set cam_pclk [ create_bd_port -dir I -type clk -freq_hz 100000000 cam_pclk ]
  set cam_vsync [ create_bd_port -dir I cam_vsync ]
  set cam_href [ create_bd_port -dir I cam_href ]
  set cam_data [ create_bd_port -dir I -from 7 -to 0 cam_data ]
  set cam_rst_n [ create_bd_port -dir O cam_rst_n ]
  set cam_pwdn [ create_bd_port -dir O cam_pwdn ]
  set pl_keys [ create_bd_port -dir I -from 1 -to 0 pl_keys ]

  # Create instance: axi_mem_intercon, and set properties
  set axi_mem_intercon [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_mem_intercon ]
  set_property -dict [list \
    CONFIG.ENABLE_ADVANCED_OPTIONS {0} \
    CONFIG.ENABLE_PROTOCOL_CHECKERS {0} \
    CONFIG.M00_HAS_DATA_FIFO {0} \
    CONFIG.M00_HAS_REGSLICE {0} \
    CONFIG.M00_ISSUANCE {0} \
    CONFIG.M00_SECURE {0} \
    CONFIG.M01_HAS_DATA_FIFO {0} \
    CONFIG.M01_HAS_REGSLICE {0} \
    CONFIG.M01_ISSUANCE {0} \
    CONFIG.M01_SECURE {0} \
    CONFIG.M02_HAS_DATA_FIFO {0} \
    CONFIG.M02_HAS_REGSLICE {0} \
    CONFIG.M02_ISSUANCE {0} \
    CONFIG.M02_SECURE {0} \
    CONFIG.M03_HAS_DATA_FIFO {0} \
    CONFIG.M03_HAS_REGSLICE {0} \
    CONFIG.M03_ISSUANCE {0} \
    CONFIG.M03_SECURE {0} \
    CONFIG.M04_HAS_DATA_FIFO {0} \
    CONFIG.M04_HAS_REGSLICE {0} \
    CONFIG.M04_ISSUANCE {0} \
    CONFIG.M04_SECURE {0} \
    CONFIG.M05_HAS_DATA_FIFO {0} \
    CONFIG.M05_HAS_REGSLICE {0} \
    CONFIG.M05_ISSUANCE {0} \
    CONFIG.M05_SECURE {0} \
    CONFIG.M06_HAS_DATA_FIFO {0} \
    CONFIG.M06_HAS_REGSLICE {0} \
    CONFIG.M06_ISSUANCE {0} \
    CONFIG.M06_SECURE {0} \
    CONFIG.M07_HAS_DATA_FIFO {0} \
    CONFIG.M07_HAS_REGSLICE {0} \
    CONFIG.M07_ISSUANCE {0} \
    CONFIG.M07_SECURE {0} \
    CONFIG.M08_HAS_DATA_FIFO {0} \
    CONFIG.M08_HAS_REGSLICE {0} \
    CONFIG.M08_ISSUANCE {0} \
    CONFIG.M08_SECURE {0} \
    CONFIG.M09_HAS_DATA_FIFO {0} \
    CONFIG.M09_HAS_REGSLICE {0} \
    CONFIG.M09_ISSUANCE {0} \
    CONFIG.M09_SECURE {0} \
    CONFIG.M10_HAS_DATA_FIFO {0} \
    CONFIG.M10_HAS_REGSLICE {0} \
    CONFIG.M10_ISSUANCE {0} \
    CONFIG.M10_SECURE {0} \
    CONFIG.M11_HAS_DATA_FIFO {0} \
    CONFIG.M11_HAS_REGSLICE {0} \
    CONFIG.M11_ISSUANCE {0} \
    CONFIG.M11_SECURE {0} \
    CONFIG.M12_HAS_DATA_FIFO {0} \
    CONFIG.M12_HAS_REGSLICE {0} \
    CONFIG.M12_ISSUANCE {0} \
    CONFIG.M12_SECURE {0} \
    CONFIG.M13_HAS_DATA_FIFO {0} \
    CONFIG.M13_HAS_REGSLICE {0} \
    CONFIG.M13_ISSUANCE {0} \
    CONFIG.M13_SECURE {0} \
    CONFIG.M14_HAS_DATA_FIFO {0} \
    CONFIG.M14_HAS_REGSLICE {0} \
    CONFIG.M14_ISSUANCE {0} \
    CONFIG.M14_SECURE {0} \
    CONFIG.M15_HAS_DATA_FIFO {0} \
    CONFIG.M15_HAS_REGSLICE {0} \
    CONFIG.M15_ISSUANCE {0} \
    CONFIG.M15_SECURE {0} \
    CONFIG.M16_HAS_DATA_FIFO {0} \
    CONFIG.M16_HAS_REGSLICE {0} \
    CONFIG.M16_ISSUANCE {0} \
    CONFIG.M16_SECURE {0} \
    CONFIG.M17_HAS_DATA_FIFO {0} \
    CONFIG.M17_HAS_REGSLICE {0} \
    CONFIG.M17_ISSUANCE {0} \
    CONFIG.M17_SECURE {0} \
    CONFIG.M18_HAS_DATA_FIFO {0} \
    CONFIG.M18_HAS_REGSLICE {0} \
    CONFIG.M18_ISSUANCE {0} \
    CONFIG.M18_SECURE {0} \
    CONFIG.M19_HAS_DATA_FIFO {0} \
    CONFIG.M19_HAS_REGSLICE {0} \
    CONFIG.M19_ISSUANCE {0} \
    CONFIG.M19_SECURE {0} \
    CONFIG.M20_HAS_DATA_FIFO {0} \
    CONFIG.M20_HAS_REGSLICE {0} \
    CONFIG.M20_ISSUANCE {0} \
    CONFIG.M20_SECURE {0} \
    CONFIG.M21_HAS_DATA_FIFO {0} \
    CONFIG.M21_HAS_REGSLICE {0} \
    CONFIG.M21_ISSUANCE {0} \
    CONFIG.M21_SECURE {0} \
    CONFIG.M22_HAS_DATA_FIFO {0} \
    CONFIG.M22_HAS_REGSLICE {0} \
    CONFIG.M22_ISSUANCE {0} \
    CONFIG.M22_SECURE {0} \
    CONFIG.M23_HAS_DATA_FIFO {0} \
    CONFIG.M23_HAS_REGSLICE {0} \
    CONFIG.M23_ISSUANCE {0} \
    CONFIG.M23_SECURE {0} \
    CONFIG.M24_HAS_DATA_FIFO {0} \
    CONFIG.M24_HAS_REGSLICE {0} \
    CONFIG.M24_ISSUANCE {0} \
    CONFIG.M24_SECURE {0} \
    CONFIG.M25_HAS_DATA_FIFO {0} \
    CONFIG.M25_HAS_REGSLICE {0} \
    CONFIG.M25_ISSUANCE {0} \
    CONFIG.M25_SECURE {0} \
    CONFIG.M26_HAS_DATA_FIFO {0} \
    CONFIG.M26_HAS_REGSLICE {0} \
    CONFIG.M26_ISSUANCE {0} \
    CONFIG.M26_SECURE {0} \
    CONFIG.M27_HAS_DATA_FIFO {0} \
    CONFIG.M27_HAS_REGSLICE {0} \
    CONFIG.M27_ISSUANCE {0} \
    CONFIG.M27_SECURE {0} \
    CONFIG.M28_HAS_DATA_FIFO {0} \
    CONFIG.M28_HAS_REGSLICE {0} \
    CONFIG.M28_ISSUANCE {0} \
    CONFIG.M28_SECURE {0} \
    CONFIG.M29_HAS_DATA_FIFO {0} \
    CONFIG.M29_HAS_REGSLICE {0} \
    CONFIG.M29_ISSUANCE {0} \
    CONFIG.M29_SECURE {0} \
    CONFIG.M30_HAS_DATA_FIFO {0} \
    CONFIG.M30_HAS_REGSLICE {0} \
    CONFIG.M30_ISSUANCE {0} \
    CONFIG.M30_SECURE {0} \
    CONFIG.M31_HAS_DATA_FIFO {0} \
    CONFIG.M31_HAS_REGSLICE {0} \
    CONFIG.M31_ISSUANCE {0} \
    CONFIG.M31_SECURE {0} \
    CONFIG.M32_HAS_DATA_FIFO {0} \
    CONFIG.M32_HAS_REGSLICE {0} \
    CONFIG.M32_ISSUANCE {0} \
    CONFIG.M32_SECURE {0} \
    CONFIG.M33_HAS_DATA_FIFO {0} \
    CONFIG.M33_HAS_REGSLICE {0} \
    CONFIG.M33_ISSUANCE {0} \
    CONFIG.M33_SECURE {0} \
    CONFIG.M34_HAS_DATA_FIFO {0} \
    CONFIG.M34_HAS_REGSLICE {0} \
    CONFIG.M34_ISSUANCE {0} \
    CONFIG.M34_SECURE {0} \
    CONFIG.M35_HAS_DATA_FIFO {0} \
    CONFIG.M35_HAS_REGSLICE {0} \
    CONFIG.M35_ISSUANCE {0} \
    CONFIG.M35_SECURE {0} \
    CONFIG.M36_HAS_DATA_FIFO {0} \
    CONFIG.M36_HAS_REGSLICE {0} \
    CONFIG.M36_ISSUANCE {0} \
    CONFIG.M36_SECURE {0} \
    CONFIG.M37_HAS_DATA_FIFO {0} \
    CONFIG.M37_HAS_REGSLICE {0} \
    CONFIG.M37_ISSUANCE {0} \
    CONFIG.M37_SECURE {0} \
    CONFIG.M38_HAS_DATA_FIFO {0} \
    CONFIG.M38_HAS_REGSLICE {0} \
    CONFIG.M38_ISSUANCE {0} \
    CONFIG.M38_SECURE {0} \
    CONFIG.M39_HAS_DATA_FIFO {0} \
    CONFIG.M39_HAS_REGSLICE {0} \
    CONFIG.M39_ISSUANCE {0} \
    CONFIG.M39_SECURE {0} \
    CONFIG.M40_HAS_DATA_FIFO {0} \
    CONFIG.M40_HAS_REGSLICE {0} \
    CONFIG.M40_ISSUANCE {0} \
    CONFIG.M40_SECURE {0} \
    CONFIG.M41_HAS_DATA_FIFO {0} \
    CONFIG.M41_HAS_REGSLICE {0} \
    CONFIG.M41_ISSUANCE {0} \
    CONFIG.M41_SECURE {0} \
    CONFIG.M42_HAS_DATA_FIFO {0} \
    CONFIG.M42_HAS_REGSLICE {0} \
    CONFIG.M42_ISSUANCE {0} \
    CONFIG.M42_SECURE {0} \
    CONFIG.M43_HAS_DATA_FIFO {0} \
    CONFIG.M43_HAS_REGSLICE {0} \
    CONFIG.M43_ISSUANCE {0} \
    CONFIG.M43_SECURE {0} \
    CONFIG.M44_HAS_DATA_FIFO {0} \
    CONFIG.M44_HAS_REGSLICE {0} \
    CONFIG.M44_ISSUANCE {0} \
    CONFIG.M44_SECURE {0} \
    CONFIG.M45_HAS_DATA_FIFO {0} \
    CONFIG.M45_HAS_REGSLICE {0} \
    CONFIG.M45_ISSUANCE {0} \
    CONFIG.M45_SECURE {0} \
    CONFIG.M46_HAS_DATA_FIFO {0} \
    CONFIG.M46_HAS_REGSLICE {0} \
    CONFIG.M46_ISSUANCE {0} \
    CONFIG.M46_SECURE {0} \
    CONFIG.M47_HAS_DATA_FIFO {0} \
    CONFIG.M47_HAS_REGSLICE {0} \
    CONFIG.M47_ISSUANCE {0} \
    CONFIG.M47_SECURE {0} \
    CONFIG.M48_HAS_DATA_FIFO {0} \
    CONFIG.M48_HAS_REGSLICE {0} \
    CONFIG.M48_ISSUANCE {0} \
    CONFIG.M48_SECURE {0} \
    CONFIG.M49_HAS_DATA_FIFO {0} \
    CONFIG.M49_HAS_REGSLICE {0} \
    CONFIG.M49_ISSUANCE {0} \
    CONFIG.M49_SECURE {0} \
    CONFIG.M50_HAS_DATA_FIFO {0} \
    CONFIG.M50_HAS_REGSLICE {0} \
    CONFIG.M50_ISSUANCE {0} \
    CONFIG.M50_SECURE {0} \
    CONFIG.M51_HAS_DATA_FIFO {0} \
    CONFIG.M51_HAS_REGSLICE {0} \
    CONFIG.M51_ISSUANCE {0} \
    CONFIG.M51_SECURE {0} \
    CONFIG.M52_HAS_DATA_FIFO {0} \
    CONFIG.M52_HAS_REGSLICE {0} \
    CONFIG.M52_ISSUANCE {0} \
    CONFIG.M52_SECURE {0} \
    CONFIG.M53_HAS_DATA_FIFO {0} \
    CONFIG.M53_HAS_REGSLICE {0} \
    CONFIG.M53_ISSUANCE {0} \
    CONFIG.M53_SECURE {0} \
    CONFIG.M54_HAS_DATA_FIFO {0} \
    CONFIG.M54_HAS_REGSLICE {0} \
    CONFIG.M54_ISSUANCE {0} \
    CONFIG.M54_SECURE {0} \
    CONFIG.M55_HAS_DATA_FIFO {0} \
    CONFIG.M55_HAS_REGSLICE {0} \
    CONFIG.M55_ISSUANCE {0} \
    CONFIG.M55_SECURE {0} \
    CONFIG.M56_HAS_DATA_FIFO {0} \
    CONFIG.M56_HAS_REGSLICE {0} \
    CONFIG.M56_ISSUANCE {0} \
    CONFIG.M56_SECURE {0} \
    CONFIG.M57_HAS_DATA_FIFO {0} \
    CONFIG.M57_HAS_REGSLICE {0} \
    CONFIG.M57_ISSUANCE {0} \
    CONFIG.M57_SECURE {0} \
    CONFIG.M58_HAS_DATA_FIFO {0} \
    CONFIG.M58_HAS_REGSLICE {0} \
    CONFIG.M58_ISSUANCE {0} \
    CONFIG.M58_SECURE {0} \
    CONFIG.M59_HAS_DATA_FIFO {0} \
    CONFIG.M59_HAS_REGSLICE {0} \
    CONFIG.M59_ISSUANCE {0} \
    CONFIG.M59_SECURE {0} \
    CONFIG.M60_HAS_DATA_FIFO {0} \
    CONFIG.M60_HAS_REGSLICE {0} \
    CONFIG.M60_ISSUANCE {0} \
    CONFIG.M60_SECURE {0} \
    CONFIG.M61_HAS_DATA_FIFO {0} \
    CONFIG.M61_HAS_REGSLICE {0} \
    CONFIG.M61_ISSUANCE {0} \
    CONFIG.M61_SECURE {0} \
    CONFIG.M62_HAS_DATA_FIFO {0} \
    CONFIG.M62_HAS_REGSLICE {0} \
    CONFIG.M62_ISSUANCE {0} \
    CONFIG.M62_SECURE {0} \
    CONFIG.M63_HAS_DATA_FIFO {0} \
    CONFIG.M63_HAS_REGSLICE {0} \
    CONFIG.M63_ISSUANCE {0} \
    CONFIG.M63_SECURE {0} \
    CONFIG.NUM_MI {1} \
    CONFIG.NUM_SI {3} \
    CONFIG.PCHK_MAX_RD_BURSTS {2} \
    CONFIG.PCHK_MAX_WR_BURSTS {2} \
    CONFIG.PCHK_WAITS {0} \
    CONFIG.S00_ARB_PRIORITY {0} \
    CONFIG.S00_HAS_DATA_FIFO {0} \
    CONFIG.S00_HAS_REGSLICE {0} \
    CONFIG.S01_ARB_PRIORITY {0} \
    CONFIG.S01_HAS_DATA_FIFO {0} \
    CONFIG.S01_HAS_REGSLICE {0} \
    CONFIG.S02_ARB_PRIORITY {0} \
    CONFIG.S02_HAS_DATA_FIFO {0} \
    CONFIG.S02_HAS_REGSLICE {0} \
    CONFIG.S03_ARB_PRIORITY {0} \
    CONFIG.S03_HAS_DATA_FIFO {0} \
    CONFIG.S03_HAS_REGSLICE {0} \
    CONFIG.S04_ARB_PRIORITY {0} \
    CONFIG.S04_HAS_DATA_FIFO {0} \
    CONFIG.S04_HAS_REGSLICE {0} \
    CONFIG.S05_ARB_PRIORITY {0} \
    CONFIG.S05_HAS_DATA_FIFO {0} \
    CONFIG.S05_HAS_REGSLICE {0} \
    CONFIG.S06_ARB_PRIORITY {0} \
    CONFIG.S06_HAS_DATA_FIFO {0} \
    CONFIG.S06_HAS_REGSLICE {0} \
    CONFIG.S07_ARB_PRIORITY {0} \
    CONFIG.S07_HAS_DATA_FIFO {0} \
    CONFIG.S07_HAS_REGSLICE {0} \
    CONFIG.S08_ARB_PRIORITY {0} \
    CONFIG.S08_HAS_DATA_FIFO {0} \
    CONFIG.S08_HAS_REGSLICE {0} \
    CONFIG.S09_ARB_PRIORITY {0} \
    CONFIG.S09_HAS_DATA_FIFO {0} \
    CONFIG.S09_HAS_REGSLICE {0} \
    CONFIG.S10_ARB_PRIORITY {0} \
    CONFIG.S10_HAS_DATA_FIFO {0} \
    CONFIG.S10_HAS_REGSLICE {0} \
    CONFIG.S11_ARB_PRIORITY {0} \
    CONFIG.S11_HAS_DATA_FIFO {0} \
    CONFIG.S11_HAS_REGSLICE {0} \
    CONFIG.S12_ARB_PRIORITY {0} \
    CONFIG.S12_HAS_DATA_FIFO {0} \
    CONFIG.S12_HAS_REGSLICE {0} \
    CONFIG.S13_ARB_PRIORITY {0} \
    CONFIG.S13_HAS_DATA_FIFO {0} \
    CONFIG.S13_HAS_REGSLICE {0} \
    CONFIG.S14_ARB_PRIORITY {0} \
    CONFIG.S14_HAS_DATA_FIFO {0} \
    CONFIG.S14_HAS_REGSLICE {0} \
    CONFIG.S15_ARB_PRIORITY {0} \
    CONFIG.S15_HAS_DATA_FIFO {0} \
    CONFIG.S15_HAS_REGSLICE {0} \
    CONFIG.STRATEGY {0} \
    CONFIG.SYNCHRONIZATION_STAGES {3} \
    CONFIG.XBAR_DATA_WIDTH {32} \
  ] $axi_mem_intercon


  # Create instance: axi_vdma_0, and set properties
  set axi_vdma_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:6.3 axi_vdma_0 ]
  set_property -dict [list \
    CONFIG.C_FAMILY {zynq} \
    CONFIG.C_SELECT_XPM {0} \
    CONFIG.c_addr_width {32} \
    CONFIG.c_dlytmr_resolution {125} \
    CONFIG.c_dynamic_resolution {1} \
    CONFIG.c_enable_all {0} \
    CONFIG.c_enable_mm2s_buf_empty {0} \
    CONFIG.c_enable_mm2s_delay_counter {1} \
    CONFIG.c_enable_mm2s_frm_counter {1} \
    CONFIG.c_enable_mm2s_frmstr_reg {0} \
    CONFIG.c_enable_mm2s_fsync_out {0} \
    CONFIG.c_enable_mm2s_param_updt {0} \
    CONFIG.c_enable_mm2s_rst_out {0} \
    CONFIG.c_enable_s2mm_buf_full {0} \
    CONFIG.c_enable_s2mm_delay_counter {1} \
    CONFIG.c_enable_s2mm_frm_counter {1} \
    CONFIG.c_enable_s2mm_frmstr_reg {0} \
    CONFIG.c_enable_s2mm_fsync_out {0} \
    CONFIG.c_enable_s2mm_param_updt {0} \
    CONFIG.c_enable_s2mm_rst_out {0} \
    CONFIG.c_enable_s2mm_sts_reg {0} \
    CONFIG.c_enable_tstvec {0} \
    CONFIG.c_enable_vert_flip {0} \
    CONFIG.c_enable_vidprmtr_reads {1} \
    CONFIG.c_flush_on_fsync {1} \
    CONFIG.c_include_internal_genlock {1} \
    CONFIG.c_include_mm2s {1} \
    CONFIG.c_include_mm2s_dre {0} \
    CONFIG.c_include_mm2s_sf {0} \
    CONFIG.c_include_s2mm {1} \
    CONFIG.c_include_s2mm_dre {0} \
    CONFIG.c_include_s2mm_sf {1} \
    CONFIG.c_include_sg {0} \
    CONFIG.c_m_axi_mm2s_data_width {64} \
    CONFIG.c_m_axi_s2mm_data_width {64} \
    CONFIG.c_m_axis_mm2s_tdata_width {24} \
    CONFIG.c_mm2s_genlock_mode {3} \
    CONFIG.c_mm2s_genlock_num_masters {1} \
    CONFIG.c_mm2s_genlock_repeat_en {0} \
    CONFIG.c_mm2s_linebuffer_depth {2048} \
    CONFIG.c_mm2s_linebuffer_thresh {4} \
    CONFIG.c_mm2s_max_burst_length {64} \
    CONFIG.c_mm2s_sof_enable {1} \
    CONFIG.c_num_fstores {3} \
    CONFIG.c_s2mm_genlock_mode {2} \
    CONFIG.c_s2mm_genlock_num_masters {1} \
    CONFIG.c_s2mm_genlock_repeat_en {1} \
    CONFIG.c_s2mm_linebuffer_depth {2048} \
    CONFIG.c_s2mm_linebuffer_thresh {4} \
    CONFIG.c_s2mm_max_burst_length {64} \
    CONFIG.c_s2mm_sof_enable {1} \
    CONFIG.c_use_fsync {1} \
    CONFIG.c_use_mm2s_fsync {0} \
    CONFIG.c_use_s2mm_fsync {2} \
  ] $axi_vdma_0


  # Create instance: axi_vdma_1, and set properties
  set axi_vdma_1 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:6.3 axi_vdma_1 ]
  set_property -dict [list \
    CONFIG.C_FAMILY {zynq} \
    CONFIG.C_SELECT_XPM {0} \
    CONFIG.c_addr_width {32} \
    CONFIG.c_dlytmr_resolution {125} \
    CONFIG.c_dynamic_resolution {1} \
    CONFIG.c_enable_all {0} \
    CONFIG.c_enable_mm2s_buf_empty {0} \
    CONFIG.c_enable_mm2s_delay_counter {1} \
    CONFIG.c_enable_mm2s_frm_counter {1} \
    CONFIG.c_enable_mm2s_frmstr_reg {0} \
    CONFIG.c_enable_mm2s_fsync_out {0} \
    CONFIG.c_enable_mm2s_param_updt {0} \
    CONFIG.c_enable_mm2s_rst_out {0} \
    CONFIG.c_enable_s2mm_buf_full {0} \
    CONFIG.c_enable_s2mm_delay_counter {1} \
    CONFIG.c_enable_s2mm_frm_counter {1} \
    CONFIG.c_enable_s2mm_frmstr_reg {0} \
    CONFIG.c_enable_s2mm_fsync_out {0} \
    CONFIG.c_enable_s2mm_param_updt {0} \
    CONFIG.c_enable_s2mm_rst_out {0} \
    CONFIG.c_enable_s2mm_sts_reg {0} \
    CONFIG.c_enable_tstvec {0} \
    CONFIG.c_enable_vert_flip {0} \
    CONFIG.c_enable_vidprmtr_reads {1} \
    CONFIG.c_flush_on_fsync {1} \
    CONFIG.c_include_internal_genlock {0} \
    CONFIG.c_include_mm2s {0} \
    CONFIG.c_include_mm2s_sf {0} \
    CONFIG.c_include_s2mm {1} \
    CONFIG.c_include_s2mm_dre {0} \
    CONFIG.c_include_s2mm_sf {1} \
    CONFIG.c_include_sg {0} \
    CONFIG.c_m_axi_s2mm_data_width {64} \
    CONFIG.c_mm2s_genlock_repeat_en {0} \
    CONFIG.c_mm2s_linebuffer_thresh {4} \
    CONFIG.c_mm2s_sof_enable {1} \
    CONFIG.c_num_fstores {2} \
    CONFIG.c_s2mm_genlock_mode {0} \
    CONFIG.c_s2mm_genlock_repeat_en {1} \
    CONFIG.c_s2mm_linebuffer_depth {2048} \
    CONFIG.c_s2mm_linebuffer_thresh {4} \
    CONFIG.c_s2mm_max_burst_length {64} \
    CONFIG.c_s2mm_sof_enable {1} \
    CONFIG.c_use_fsync {1} \
    CONFIG.c_use_s2mm_fsync {2} \
  ] $axi_vdma_1


  # Create instance: clk_wiz_0, and set properties
  set clk_wiz_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 clk_wiz_0 ]
  set_property -dict [list \
    CONFIG.AUTO_PRIMITIVE {MMCM} \
    CONFIG.AXI_DRP {false} \
    CONFIG.CALC_DONE {empty} \
    CONFIG.CDDCDONE_PORT {cddcdone} \
    CONFIG.CDDCREQ_PORT {cddcreq} \
    CONFIG.CLKFB_IN_N_PORT {clkfb_in_n} \
    CONFIG.CLKFB_IN_PORT {clkfb_in} \
    CONFIG.CLKFB_IN_P_PORT {clkfb_in_p} \
    CONFIG.CLKFB_IN_SIGNALING {SINGLE} \
    CONFIG.CLKFB_OUT_N_PORT {clkfb_out_n} \
    CONFIG.CLKFB_OUT_PORT {clkfb_out} \
    CONFIG.CLKFB_OUT_P_PORT {clkfb_out_p} \
    CONFIG.CLKFB_STOPPED_PORT {clkfb_stopped} \
    CONFIG.CLKIN1_JITTER_PS {100.0} \
    CONFIG.CLKIN1_UI_JITTER {0.010} \
    CONFIG.CLKIN2_JITTER_PS {100.0} \
    CONFIG.CLKIN2_UI_JITTER {0.010} \
    CONFIG.CLKOUT1_DRIVES {BUFG} \
    CONFIG.CLKOUT1_JITTER {152.549} \
    CONFIG.CLKOUT1_MATCHED_ROUTING {false} \
    CONFIG.CLKOUT1_PHASE_ERROR {116.405} \
    CONFIG.CLKOUT1_REQUESTED_DUTY_CYCLE {50.000} \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {75.000} \
    CONFIG.CLKOUT1_REQUESTED_PHASE {0.000} \
    CONFIG.CLKOUT1_SEQUENCE_NUMBER {1} \
    CONFIG.CLKOUT1_USED {true} \
    CONFIG.CLKOUT2_DRIVES {BUFG} \
    CONFIG.CLKOUT2_JITTER {111.604} \
    CONFIG.CLKOUT2_MATCHED_ROUTING {false} \
    CONFIG.CLKOUT2_PHASE_ERROR {116.405} \
    CONFIG.CLKOUT2_REQUESTED_DUTY_CYCLE {50.000} \
    CONFIG.CLKOUT2_REQUESTED_OUT_FREQ {375.000} \
    CONFIG.CLKOUT2_REQUESTED_PHASE {0.000} \
    CONFIG.CLKOUT2_SEQUENCE_NUMBER {1} \
    CONFIG.CLKOUT2_USED {true} \
    CONFIG.CLKOUT3_DRIVES {BUFG} \
    CONFIG.CLKOUT3_JITTER {132.464} \
    CONFIG.CLKOUT3_MATCHED_ROUTING {false} \
    CONFIG.CLKOUT3_PHASE_ERROR {116.405} \
    CONFIG.CLKOUT3_REQUESTED_DUTY_CYCLE {50.000} \
    CONFIG.CLKOUT3_REQUESTED_OUT_FREQ {150.000} \
    CONFIG.CLKOUT3_REQUESTED_PHASE {0.000} \
    CONFIG.CLKOUT3_SEQUENCE_NUMBER {1} \
    CONFIG.CLKOUT3_USED {true} \
    CONFIG.CLKOUT4_DRIVES {BUFG} \
    CONFIG.CLKOUT4_JITTER {0.0} \
    CONFIG.CLKOUT4_MATCHED_ROUTING {false} \
    CONFIG.CLKOUT4_PHASE_ERROR {0.0} \
    CONFIG.CLKOUT4_REQUESTED_DUTY_CYCLE {50.000} \
    CONFIG.CLKOUT4_REQUESTED_OUT_FREQ {100.000} \
    CONFIG.CLKOUT4_REQUESTED_PHASE {0.000} \
    CONFIG.CLKOUT4_SEQUENCE_NUMBER {1} \
    CONFIG.CLKOUT4_USED {false} \
    CONFIG.CLKOUT5_DRIVES {BUFG} \
    CONFIG.CLKOUT5_JITTER {0.0} \
    CONFIG.CLKOUT5_MATCHED_ROUTING {false} \
    CONFIG.CLKOUT5_PHASE_ERROR {0.0} \
    CONFIG.CLKOUT5_REQUESTED_DUTY_CYCLE {50.000} \
    CONFIG.CLKOUT5_REQUESTED_OUT_FREQ {100.000} \
    CONFIG.CLKOUT5_REQUESTED_PHASE {0.000} \
    CONFIG.CLKOUT5_SEQUENCE_NUMBER {1} \
    CONFIG.CLKOUT5_USED {false} \
    CONFIG.CLKOUT6_DRIVES {BUFG} \
    CONFIG.CLKOUT6_JITTER {0.0} \
    CONFIG.CLKOUT6_MATCHED_ROUTING {false} \
    CONFIG.CLKOUT6_PHASE_ERROR {0.0} \
    CONFIG.CLKOUT6_REQUESTED_DUTY_CYCLE {50.000} \
    CONFIG.CLKOUT6_REQUESTED_OUT_FREQ {100.000} \
    CONFIG.CLKOUT6_REQUESTED_PHASE {0.000} \
    CONFIG.CLKOUT6_SEQUENCE_NUMBER {1} \
    CONFIG.CLKOUT6_USED {false} \
    CONFIG.CLKOUT7_DRIVES {BUFG} \
    CONFIG.CLKOUT7_JITTER {0.0} \
    CONFIG.CLKOUT7_MATCHED_ROUTING {false} \
    CONFIG.CLKOUT7_PHASE_ERROR {0.0} \
    CONFIG.CLKOUT7_REQUESTED_DUTY_CYCLE {50.000} \
    CONFIG.CLKOUT7_REQUESTED_OUT_FREQ {100.000} \
    CONFIG.CLKOUT7_REQUESTED_PHASE {0.000} \
    CONFIG.CLKOUT7_SEQUENCE_NUMBER {1} \
    CONFIG.CLKOUT7_USED {false} \
    CONFIG.CLKOUTPHY_REQUESTED_FREQ {600.000} \
    CONFIG.CLK_IN1_BOARD_INTERFACE {Custom} \
    CONFIG.CLK_IN2_BOARD_INTERFACE {Custom} \
    CONFIG.CLK_IN_SEL_PORT {clk_in_sel} \
    CONFIG.CLK_OUT1_PORT {clk_out1} \
    CONFIG.CLK_OUT1_USE_FINE_PS_GUI {false} \
    CONFIG.CLK_OUT2_PORT {clk_out2} \
    CONFIG.CLK_OUT2_USE_FINE_PS_GUI {false} \
    CONFIG.CLK_OUT3_PORT {clk_out3} \
    CONFIG.CLK_OUT3_USE_FINE_PS_GUI {false} \
    CONFIG.CLK_OUT4_PORT {clk_out4} \
    CONFIG.CLK_OUT4_USE_FINE_PS_GUI {false} \
    CONFIG.CLK_OUT5_PORT {clk_out5} \
    CONFIG.CLK_OUT5_USE_FINE_PS_GUI {false} \
    CONFIG.CLK_OUT6_PORT {clk_out6} \
    CONFIG.CLK_OUT6_USE_FINE_PS_GUI {false} \
    CONFIG.CLK_OUT7_PORT {clk_out7} \
    CONFIG.CLK_OUT7_USE_FINE_PS_GUI {false} \
    CONFIG.CLK_VALID_PORT {CLK_VALID} \
    CONFIG.CLOCK_MGR_TYPE {auto} \
    CONFIG.DADDR_PORT {daddr} \
    CONFIG.DCLK_PORT {dclk} \
    CONFIG.DEN_PORT {den} \
    CONFIG.DIFF_CLK_IN1_BOARD_INTERFACE {Custom} \
    CONFIG.DIFF_CLK_IN2_BOARD_INTERFACE {Custom} \
    CONFIG.DIN_PORT {din} \
    CONFIG.DOUT_PORT {dout} \
    CONFIG.DRDY_PORT {drdy} \
    CONFIG.DWE_PORT {dwe} \
    CONFIG.ENABLE_CDDC {false} \
    CONFIG.ENABLE_CLKOUTPHY {false} \
    CONFIG.ENABLE_CLOCK_MONITOR {false} \
    CONFIG.ENABLE_USER_CLOCK0 {false} \
    CONFIG.ENABLE_USER_CLOCK1 {false} \
    CONFIG.ENABLE_USER_CLOCK2 {false} \
    CONFIG.ENABLE_USER_CLOCK3 {false} \
    CONFIG.Enable_PLL0 {false} \
    CONFIG.Enable_PLL1 {false} \
    CONFIG.FEEDBACK_SOURCE {FDBK_AUTO} \
    CONFIG.INPUT_CLK_STOPPED_PORT {input_clk_stopped} \
    CONFIG.INPUT_MODE {frequency} \
    CONFIG.INTERFACE_SELECTION {Enable_AXI} \
    CONFIG.IN_FREQ_UNITS {Units_MHz} \
    CONFIG.IN_JITTER_UNITS {Units_UI} \
    CONFIG.JITTER_OPTIONS {UI} \
    CONFIG.JITTER_SEL {No_Jitter} \
    CONFIG.LOCKED_PORT {locked} \
    CONFIG.MMCM_BANDWIDTH {OPTIMIZED} \
    CONFIG.MMCM_CLKFBOUT_MULT_F {7.500} \
    CONFIG.MMCM_CLKFBOUT_PHASE {0.000} \
    CONFIG.MMCM_CLKFBOUT_USE_FINE_PS {false} \
    CONFIG.MMCM_CLKIN1_PERIOD {10.000} \
    CONFIG.MMCM_CLKIN2_PERIOD {10.000} \
    CONFIG.MMCM_CLKOUT0_DIVIDE_F {10.000} \
    CONFIG.MMCM_CLKOUT0_DUTY_CYCLE {0.500} \
    CONFIG.MMCM_CLKOUT0_PHASE {0.000} \
    CONFIG.MMCM_CLKOUT0_USE_FINE_PS {false} \
    CONFIG.MMCM_CLKOUT1_DIVIDE {2} \
    CONFIG.MMCM_CLKOUT1_DUTY_CYCLE {0.500} \
    CONFIG.MMCM_CLKOUT1_PHASE {0.000} \
    CONFIG.MMCM_CLKOUT1_USE_FINE_PS {false} \
    CONFIG.MMCM_CLKOUT2_DIVIDE {5} \
    CONFIG.MMCM_CLKOUT2_DUTY_CYCLE {0.500} \
    CONFIG.MMCM_CLKOUT2_PHASE {0.000} \
    CONFIG.MMCM_CLKOUT2_USE_FINE_PS {false} \
    CONFIG.MMCM_CLKOUT3_DIVIDE {1} \
    CONFIG.MMCM_CLKOUT3_DUTY_CYCLE {0.500} \
    CONFIG.MMCM_CLKOUT3_PHASE {0.000} \
    CONFIG.MMCM_CLKOUT3_USE_FINE_PS {false} \
    CONFIG.MMCM_CLKOUT4_CASCADE {false} \
    CONFIG.MMCM_CLKOUT4_DIVIDE {1} \
    CONFIG.MMCM_CLKOUT4_DUTY_CYCLE {0.500} \
    CONFIG.MMCM_CLKOUT4_PHASE {0.000} \
    CONFIG.MMCM_CLKOUT4_USE_FINE_PS {false} \
    CONFIG.MMCM_CLKOUT5_DIVIDE {1} \
    CONFIG.MMCM_CLKOUT5_DUTY_CYCLE {0.500} \
    CONFIG.MMCM_CLKOUT5_PHASE {0.000} \
    CONFIG.MMCM_CLKOUT5_USE_FINE_PS {false} \
    CONFIG.MMCM_CLKOUT6_DIVIDE {1} \
    CONFIG.MMCM_CLKOUT6_DUTY_CYCLE {0.500} \
    CONFIG.MMCM_CLKOUT6_PHASE {0.000} \
    CONFIG.MMCM_CLKOUT6_USE_FINE_PS {false} \
    CONFIG.MMCM_CLOCK_HOLD {false} \
    CONFIG.MMCM_COMPENSATION {ZHOLD} \
    CONFIG.MMCM_DIVCLK_DIVIDE {1} \
    CONFIG.MMCM_NOTES {None} \
    CONFIG.MMCM_REF_JITTER1 {0.010} \
    CONFIG.MMCM_REF_JITTER2 {0.010} \
    CONFIG.MMCM_STARTUP_WAIT {false} \
    CONFIG.NUM_OUT_CLKS {3} \
    CONFIG.OPTIMIZE_CLOCKING_STRUCTURE_EN {false} \
    CONFIG.OVERRIDE_MMCM {false} \
    CONFIG.OVERRIDE_PLL {false} \
    CONFIG.PHASESHIFT_MODE {WAVEFORM} \
    CONFIG.PHASE_DUTY_CONFIG {false} \
    CONFIG.PLATFORM {UNKNOWN} \
    CONFIG.PLL_BANDWIDTH {OPTIMIZED} \
    CONFIG.PLL_CLKFBOUT_MULT {4} \
    CONFIG.PLL_CLKFBOUT_PHASE {0.000} \
    CONFIG.PLL_CLKIN_PERIOD {10.000} \
    CONFIG.PLL_CLKOUT0_DIVIDE {1} \
    CONFIG.PLL_CLKOUT0_DUTY_CYCLE {0.500} \
    CONFIG.PLL_CLKOUT0_PHASE {0.000} \
    CONFIG.PLL_CLKOUT1_DIVIDE {1} \
    CONFIG.PLL_CLKOUT1_DUTY_CYCLE {0.500} \
    CONFIG.PLL_CLKOUT1_PHASE {0.000} \
    CONFIG.PLL_CLKOUT2_DIVIDE {1} \
    CONFIG.PLL_CLKOUT2_DUTY_CYCLE {0.500} \
    CONFIG.PLL_CLKOUT2_PHASE {0.000} \
    CONFIG.PLL_CLKOUT3_DIVIDE {1} \
    CONFIG.PLL_CLKOUT3_DUTY_CYCLE {0.500} \
    CONFIG.PLL_CLKOUT3_PHASE {0.000} \
    CONFIG.PLL_CLKOUT4_DIVIDE {1} \
    CONFIG.PLL_CLKOUT4_DUTY_CYCLE {0.500} \
    CONFIG.PLL_CLKOUT4_PHASE {0.000} \
    CONFIG.PLL_CLKOUT5_DIVIDE {1} \
    CONFIG.PLL_CLKOUT5_DUTY_CYCLE {0.500} \
    CONFIG.PLL_CLKOUT5_PHASE {0.000} \
    CONFIG.PLL_CLK_FEEDBACK {CLKFBOUT} \
    CONFIG.PLL_COMPENSATION {SYSTEM_SYNCHRONOUS} \
    CONFIG.PLL_DIVCLK_DIVIDE {1} \
    CONFIG.PLL_NOTES {None} \
    CONFIG.PLL_REF_JITTER {0.010} \
    CONFIG.POWER_DOWN_PORT {power_down} \
    CONFIG.PRECISION {1} \
    CONFIG.PRIMARY_PORT {clk_in1} \
    CONFIG.PRIMITIVE {MMCM} \
    CONFIG.PRIMTYPE_SEL {mmcm_adv} \
    CONFIG.PRIM_IN_FREQ {100.000} \
    CONFIG.PRIM_IN_JITTER {0.010} \
    CONFIG.PRIM_IN_TIMEPERIOD {10.000} \
    CONFIG.PRIM_SOURCE {No_buffer} \
    CONFIG.PSCLK_PORT {psclk} \
    CONFIG.PSDONE_PORT {psdone} \
    CONFIG.PSEN_PORT {psen} \
    CONFIG.PSINCDEC_PORT {psincdec} \
    CONFIG.REF_CLK_FREQ {100.0} \
    CONFIG.RELATIVE_INCLK {REL_PRIMARY} \
    CONFIG.RESET_BOARD_INTERFACE {Custom} \
    CONFIG.RESET_PORT {reset} \
    CONFIG.RESET_TYPE {ACTIVE_HIGH} \
    CONFIG.SECONDARY_IN_FREQ {100.000} \
    CONFIG.SECONDARY_IN_JITTER {0.010} \
    CONFIG.SECONDARY_IN_TIMEPERIOD {10.000} \
    CONFIG.SECONDARY_PORT {clk_in2} \
    CONFIG.SECONDARY_SOURCE {Single_ended_clock_capable_pin} \
    CONFIG.SS_MODE {CENTER_HIGH} \
    CONFIG.SS_MOD_FREQ {250} \
    CONFIG.SS_MOD_TIME {0.004} \
    CONFIG.STATUS_PORT {STATUS} \
    CONFIG.SUMMARY_STRINGS {empty} \
    CONFIG.USER_CLK_FREQ0 {100.0} \
    CONFIG.USER_CLK_FREQ1 {100.0} \
    CONFIG.USER_CLK_FREQ2 {100.0} \
    CONFIG.USER_CLK_FREQ3 {100.0} \
    CONFIG.USE_BOARD_FLOW {false} \
    CONFIG.USE_CLKFB_STOPPED {false} \
    CONFIG.USE_CLK_VALID {false} \
    CONFIG.USE_CLOCK_SEQUENCING {false} \
    CONFIG.USE_DYN_PHASE_SHIFT {false} \
    CONFIG.USE_DYN_RECONFIG {false} \
    CONFIG.USE_FREEZE {false} \
    CONFIG.USE_FREQ_SYNTH {true} \
    CONFIG.USE_INCLK_STOPPED {false} \
    CONFIG.USE_INCLK_SWITCHOVER {false} \
    CONFIG.USE_LOCKED {true} \
    CONFIG.USE_MAX_I_JITTER {false} \
    CONFIG.USE_MIN_O_JITTER {false} \
    CONFIG.USE_MIN_POWER {false} \
    CONFIG.USE_PHASE_ALIGNMENT {true} \
    CONFIG.USE_POWER_DOWN {false} \
    CONFIG.USE_RESET {true} \
    CONFIG.USE_SAFE_CLOCK_STARTUP {false} \
    CONFIG.USE_SPREAD_SPECTRUM {false} \
    CONFIG.USE_STATUS {false} \
  ] $clk_wiz_0


  # Create instance: live_osd_0, and set properties
  set block_name display_status
  set block_cell_name live_osd_0
  if { [catch {set live_osd_0 [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $live_osd_0 eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
    set_property -dict [list \
    CONFIG.HEIGHT {720} \
    CONFIG.PIXEL_HZ {75000000} \
    CONFIG.WIDTH {1280} \
  ] $live_osd_0


  # Create instance: ov5640_capture_data_0, and set properties
  set ov5640_capture_data_0 [ create_bd_cell -type ip -vlnv alientek.com:user:ov5640_capture_data:1.0 ov5640_capture_data_0 ]

  # Create instance: processing_system7_0, and set properties
  set processing_system7_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0 ]
  set_property -dict [list \
    CONFIG.PCW_ACT_APU_PERIPHERAL_FREQMHZ {666.666687} \
    CONFIG.PCW_ACT_CAN0_PERIPHERAL_FREQMHZ {23.8095} \
    CONFIG.PCW_ACT_CAN1_PERIPHERAL_FREQMHZ {23.8095} \
    CONFIG.PCW_ACT_CAN_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_DCI_PERIPHERAL_FREQMHZ {10.158730} \
    CONFIG.PCW_ACT_ENET0_PERIPHERAL_FREQMHZ {125.000000} \
    CONFIG.PCW_ACT_ENET1_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ {100.000000} \
    CONFIG.PCW_ACT_FPGA1_PERIPHERAL_FREQMHZ {142.857132} \
    CONFIG.PCW_ACT_FPGA2_PERIPHERAL_FREQMHZ {100.000000} \
    CONFIG.PCW_ACT_FPGA3_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_I2C_PERIPHERAL_FREQMHZ {50} \
    CONFIG.PCW_ACT_PCAP_PERIPHERAL_FREQMHZ {200.000000} \
    CONFIG.PCW_ACT_QSPI_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_SDIO_PERIPHERAL_FREQMHZ {100.000000} \
    CONFIG.PCW_ACT_SMC_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_SPI_PERIPHERAL_FREQMHZ {10.000000} \
    CONFIG.PCW_ACT_TPIU_PERIPHERAL_FREQMHZ {200.000000} \
    CONFIG.PCW_ACT_TTC0_CLK0_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_ACT_TTC0_CLK1_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_ACT_TTC0_CLK2_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_ACT_TTC1_CLK0_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_ACT_TTC1_CLK1_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_ACT_TTC1_CLK2_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_ACT_TTC_PERIPHERAL_FREQMHZ {50} \
    CONFIG.PCW_ACT_UART_PERIPHERAL_FREQMHZ {100.000000} \
    CONFIG.PCW_ACT_USB0_PERIPHERAL_FREQMHZ {60} \
    CONFIG.PCW_ACT_USB1_PERIPHERAL_FREQMHZ {60} \
    CONFIG.PCW_ACT_WDT_PERIPHERAL_FREQMHZ {111.111115} \
    CONFIG.PCW_APU_CLK_RATIO_ENABLE {6:2:1} \
    CONFIG.PCW_APU_PERIPHERAL_FREQMHZ {666.666666} \
    CONFIG.PCW_CAN0_PERIPHERAL_CLKSRC {External} \
    CONFIG.PCW_CAN0_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_CAN1_PERIPHERAL_CLKSRC {External} \
    CONFIG.PCW_CAN1_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_CAN_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_CAN_PERIPHERAL_VALID {0} \
    CONFIG.PCW_CLK0_FREQ {100000000} \
    CONFIG.PCW_CLK1_FREQ {142857132} \
    CONFIG.PCW_CLK2_FREQ {100000000} \
    CONFIG.PCW_CLK3_FREQ {10000000} \
    CONFIG.PCW_CPU_CPU_6X4X_MAX_RANGE {767} \
    CONFIG.PCW_CPU_PERIPHERAL_CLKSRC {ARM PLL} \
    CONFIG.PCW_CRYSTAL_PERIPHERAL_FREQMHZ {33.333333} \
    CONFIG.PCW_DCI_PERIPHERAL_CLKSRC {DDR PLL} \
    CONFIG.PCW_DCI_PERIPHERAL_FREQMHZ {10.159} \
    CONFIG.PCW_DDR_PERIPHERAL_CLKSRC {DDR PLL} \
    CONFIG.PCW_DDR_RAM_BASEADDR {0x00100000} \
    CONFIG.PCW_DDR_RAM_HIGHADDR {0x3FFFFFFF} \
    CONFIG.PCW_DM_WIDTH {4} \
    CONFIG.PCW_DQS_WIDTH {4} \
    CONFIG.PCW_DQ_WIDTH {32} \
    CONFIG.PCW_ENET0_BASEADDR {0xE000B000} \
    CONFIG.PCW_ENET0_ENET0_IO {MIO 16 .. 27} \
    CONFIG.PCW_ENET0_GRP_MDIO_ENABLE {1} \
    CONFIG.PCW_ENET0_GRP_MDIO_IO {MIO 52 .. 53} \
    CONFIG.PCW_ENET0_HIGHADDR {0xE000BFFF} \
    CONFIG.PCW_ENET0_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_ENET0_PERIPHERAL_ENABLE {1} \
    CONFIG.PCW_ENET0_PERIPHERAL_FREQMHZ {1000 Mbps} \
    CONFIG.PCW_ENET1_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_ENET1_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_ENET_RESET_POLARITY {Active Low} \
    CONFIG.PCW_EN_4K_TIMER {0} \
    CONFIG.PCW_EN_CAN0 {0} \
    CONFIG.PCW_EN_CAN1 {0} \
    CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_EN_CLK1_PORT {1} \
    CONFIG.PCW_EN_CLK2_PORT {1} \
    CONFIG.PCW_EN_CLK3_PORT {0} \
    CONFIG.PCW_EN_CLKTRIG0_PORT {0} \
    CONFIG.PCW_EN_CLKTRIG1_PORT {0} \
    CONFIG.PCW_EN_CLKTRIG2_PORT {0} \
    CONFIG.PCW_EN_CLKTRIG3_PORT {0} \
    CONFIG.PCW_EN_DDR {1} \
    CONFIG.PCW_EN_EMIO_CAN0 {0} \
    CONFIG.PCW_EN_EMIO_CAN1 {0} \
    CONFIG.PCW_EN_EMIO_CD_SDIO0 {0} \
    CONFIG.PCW_EN_EMIO_CD_SDIO1 {0} \
    CONFIG.PCW_EN_EMIO_ENET0 {0} \
    CONFIG.PCW_EN_EMIO_ENET1 {0} \
    CONFIG.PCW_EN_EMIO_GPIO {1} \
    CONFIG.PCW_EN_EMIO_I2C0 {0} \
    CONFIG.PCW_EN_EMIO_I2C1 {0} \
    CONFIG.PCW_EN_EMIO_MODEM_UART0 {0} \
    CONFIG.PCW_EN_EMIO_MODEM_UART1 {0} \
    CONFIG.PCW_EN_EMIO_PJTAG {0} \
    CONFIG.PCW_EN_EMIO_SDIO0 {0} \
    CONFIG.PCW_EN_EMIO_SDIO1 {0} \
    CONFIG.PCW_EN_EMIO_SPI0 {0} \
    CONFIG.PCW_EN_EMIO_SPI1 {0} \
    CONFIG.PCW_EN_EMIO_SRAM_INT {0} \
    CONFIG.PCW_EN_EMIO_TRACE {0} \
    CONFIG.PCW_EN_EMIO_TTC0 {0} \
    CONFIG.PCW_EN_EMIO_TTC1 {0} \
    CONFIG.PCW_EN_EMIO_UART0 {0} \
    CONFIG.PCW_EN_EMIO_UART1 {0} \
    CONFIG.PCW_EN_EMIO_WDT {0} \
    CONFIG.PCW_EN_EMIO_WP_SDIO0 {0} \
    CONFIG.PCW_EN_EMIO_WP_SDIO1 {0} \
    CONFIG.PCW_EN_ENET0 {1} \
    CONFIG.PCW_EN_ENET1 {0} \
    CONFIG.PCW_EN_GPIO {0} \
    CONFIG.PCW_EN_I2C0 {0} \
    CONFIG.PCW_EN_I2C1 {0} \
    CONFIG.PCW_EN_MODEM_UART0 {0} \
    CONFIG.PCW_EN_MODEM_UART1 {0} \
    CONFIG.PCW_EN_PJTAG {0} \
    CONFIG.PCW_EN_PTP_ENET0 {0} \
    CONFIG.PCW_EN_PTP_ENET1 {0} \
    CONFIG.PCW_EN_QSPI {0} \
    CONFIG.PCW_EN_RST0_PORT {1} \
    CONFIG.PCW_EN_RST1_PORT {0} \
    CONFIG.PCW_EN_RST2_PORT {1} \
    CONFIG.PCW_EN_RST3_PORT {0} \
    CONFIG.PCW_EN_SDIO0 {1} \
    CONFIG.PCW_EN_SDIO1 {0} \
    CONFIG.PCW_EN_SMC {0} \
    CONFIG.PCW_EN_SPI0 {0} \
    CONFIG.PCW_EN_SPI1 {0} \
    CONFIG.PCW_EN_TRACE {0} \
    CONFIG.PCW_EN_TTC0 {0} \
    CONFIG.PCW_EN_TTC1 {0} \
    CONFIG.PCW_EN_UART0 {1} \
    CONFIG.PCW_EN_UART1 {0} \
    CONFIG.PCW_EN_USB0 {0} \
    CONFIG.PCW_EN_USB1 {0} \
    CONFIG.PCW_EN_WDT {0} \
    CONFIG.PCW_FCLK0_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_FCLK1_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_FCLK2_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_FCLK3_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_FCLK_CLK0_BUF {FALSE} \
    CONFIG.PCW_FCLK_CLK1_BUF {TRUE} \
    CONFIG.PCW_FCLK_CLK2_BUF {TRUE} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} \
    CONFIG.PCW_FPGA1_PERIPHERAL_FREQMHZ {150} \
    CONFIG.PCW_FPGA2_PERIPHERAL_FREQMHZ {100.000000} \
    CONFIG.PCW_FPGA3_PERIPHERAL_FREQMHZ {50} \
    CONFIG.PCW_FPGA_FCLK0_ENABLE {1} \
    CONFIG.PCW_FPGA_FCLK1_ENABLE {1} \
    CONFIG.PCW_FPGA_FCLK2_ENABLE {1} \
    CONFIG.PCW_GP0_EN_MODIFIABLE_TXN {1} \
    CONFIG.PCW_GP0_NUM_READ_THREADS {4} \
    CONFIG.PCW_GP0_NUM_WRITE_THREADS {4} \
    CONFIG.PCW_GP1_EN_MODIFIABLE_TXN {1} \
    CONFIG.PCW_GP1_NUM_READ_THREADS {4} \
    CONFIG.PCW_GP1_NUM_WRITE_THREADS {4} \
    CONFIG.PCW_GPIO_EMIO_GPIO_ENABLE {1} \
    CONFIG.PCW_GPIO_EMIO_GPIO_IO {2} \
    CONFIG.PCW_GPIO_EMIO_GPIO_WIDTH {2} \
    CONFIG.PCW_GPIO_MIO_GPIO_ENABLE {0} \
    CONFIG.PCW_GPIO_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_I2C0_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_I2C1_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_I2C_RESET_POLARITY {Active Low} \
    CONFIG.PCW_IMPORT_BOARD_PRESET {None} \
    CONFIG.PCW_INCLUDE_ACP_TRANS_CHECK {0} \
    CONFIG.PCW_IRQ_F2P_MODE {DIRECT} \
    CONFIG.PCW_MIO_10_IOTYPE {LVCMOS 3.3V} \
    CONFIG.PCW_MIO_10_PULLUP {enabled} \
    CONFIG.PCW_MIO_10_SLEW {slow} \
    CONFIG.PCW_MIO_14_IOTYPE {LVCMOS 3.3V} \
    CONFIG.PCW_MIO_14_PULLUP {enabled} \
    CONFIG.PCW_MIO_14_SLEW {slow} \
    CONFIG.PCW_MIO_15_IOTYPE {LVCMOS 3.3V} \
    CONFIG.PCW_MIO_15_PULLUP {enabled} \
    CONFIG.PCW_MIO_15_SLEW {slow} \
    CONFIG.PCW_MIO_16_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_16_PULLUP {enabled} \
    CONFIG.PCW_MIO_16_SLEW {slow} \
    CONFIG.PCW_MIO_17_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_17_PULLUP {enabled} \
    CONFIG.PCW_MIO_17_SLEW {slow} \
    CONFIG.PCW_MIO_18_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_18_PULLUP {enabled} \
    CONFIG.PCW_MIO_18_SLEW {slow} \
    CONFIG.PCW_MIO_19_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_19_PULLUP {enabled} \
    CONFIG.PCW_MIO_19_SLEW {slow} \
    CONFIG.PCW_MIO_20_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_20_PULLUP {enabled} \
    CONFIG.PCW_MIO_20_SLEW {slow} \
    CONFIG.PCW_MIO_21_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_21_PULLUP {enabled} \
    CONFIG.PCW_MIO_21_SLEW {slow} \
    CONFIG.PCW_MIO_22_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_22_PULLUP {enabled} \
    CONFIG.PCW_MIO_22_SLEW {slow} \
    CONFIG.PCW_MIO_23_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_23_PULLUP {enabled} \
    CONFIG.PCW_MIO_23_SLEW {slow} \
    CONFIG.PCW_MIO_24_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_24_PULLUP {enabled} \
    CONFIG.PCW_MIO_24_SLEW {slow} \
    CONFIG.PCW_MIO_25_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_25_PULLUP {enabled} \
    CONFIG.PCW_MIO_25_SLEW {slow} \
    CONFIG.PCW_MIO_26_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_26_PULLUP {enabled} \
    CONFIG.PCW_MIO_26_SLEW {slow} \
    CONFIG.PCW_MIO_27_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_27_PULLUP {enabled} \
    CONFIG.PCW_MIO_27_SLEW {slow} \
    CONFIG.PCW_MIO_40_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_40_PULLUP {enabled} \
    CONFIG.PCW_MIO_40_SLEW {slow} \
    CONFIG.PCW_MIO_41_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_41_PULLUP {enabled} \
    CONFIG.PCW_MIO_41_SLEW {slow} \
    CONFIG.PCW_MIO_42_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_42_PULLUP {enabled} \
    CONFIG.PCW_MIO_42_SLEW {slow} \
    CONFIG.PCW_MIO_43_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_43_PULLUP {enabled} \
    CONFIG.PCW_MIO_43_SLEW {slow} \
    CONFIG.PCW_MIO_44_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_44_PULLUP {enabled} \
    CONFIG.PCW_MIO_44_SLEW {slow} \
    CONFIG.PCW_MIO_45_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_45_PULLUP {enabled} \
    CONFIG.PCW_MIO_45_SLEW {slow} \
    CONFIG.PCW_MIO_52_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_52_PULLUP {enabled} \
    CONFIG.PCW_MIO_52_SLEW {slow} \
    CONFIG.PCW_MIO_53_IOTYPE {LVCMOS 1.8V} \
    CONFIG.PCW_MIO_53_PULLUP {enabled} \
    CONFIG.PCW_MIO_53_SLEW {slow} \
    CONFIG.PCW_MIO_PRIMITIVE {54} \
    CONFIG.PCW_MIO_TREE_PERIPHERALS {unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#SD 0#unassigned#unassigned#unassigned#UART 0#UART 0#Enet\
0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#SD\
0#SD 0#SD 0#SD 0#SD 0#SD 0#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#Enet 0#Enet 0} \
    CONFIG.PCW_MIO_TREE_SIGNALS {unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#cd#unassigned#unassigned#unassigned#rx#tx#tx_clk#txd[0]#txd[1]#txd[2]#txd[3]#tx_ctl#rx_clk#rxd[0]#rxd[1]#rxd[2]#rxd[3]#rx_ctl#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#clk#cmd#data[0]#data[1]#data[2]#data[3]#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#mdc#mdio}\
\
    CONFIG.PCW_M_AXI_GP0_ENABLE_STATIC_REMAP {0} \
    CONFIG.PCW_M_AXI_GP0_ID_WIDTH {12} \
    CONFIG.PCW_M_AXI_GP0_SUPPORT_NARROW_BURST {0} \
    CONFIG.PCW_M_AXI_GP0_THREAD_ID_WIDTH {12} \
    CONFIG.PCW_M_AXI_GP1_ENABLE_STATIC_REMAP {0} \
    CONFIG.PCW_M_AXI_GP1_ID_WIDTH {12} \
    CONFIG.PCW_M_AXI_GP1_SUPPORT_NARROW_BURST {0} \
    CONFIG.PCW_M_AXI_GP1_THREAD_ID_WIDTH {12} \
    CONFIG.PCW_NAND_CYCLES_T_AR {1} \
    CONFIG.PCW_NAND_CYCLES_T_CLR {1} \
    CONFIG.PCW_NAND_CYCLES_T_RC {11} \
    CONFIG.PCW_NAND_CYCLES_T_REA {1} \
    CONFIG.PCW_NAND_CYCLES_T_RR {1} \
    CONFIG.PCW_NAND_CYCLES_T_WC {11} \
    CONFIG.PCW_NAND_CYCLES_T_WP {1} \
    CONFIG.PCW_NAND_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_NOR_CS0_T_CEOE {1} \
    CONFIG.PCW_NOR_CS0_T_PC {1} \
    CONFIG.PCW_NOR_CS0_T_RC {11} \
    CONFIG.PCW_NOR_CS0_T_TR {1} \
    CONFIG.PCW_NOR_CS0_T_WC {11} \
    CONFIG.PCW_NOR_CS0_T_WP {1} \
    CONFIG.PCW_NOR_CS0_WE_TIME {0} \
    CONFIG.PCW_NOR_CS1_T_CEOE {1} \
    CONFIG.PCW_NOR_CS1_T_PC {1} \
    CONFIG.PCW_NOR_CS1_T_RC {11} \
    CONFIG.PCW_NOR_CS1_T_TR {1} \
    CONFIG.PCW_NOR_CS1_T_WC {11} \
    CONFIG.PCW_NOR_CS1_T_WP {1} \
    CONFIG.PCW_NOR_CS1_WE_TIME {0} \
    CONFIG.PCW_NOR_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_NOR_SRAM_CS0_T_CEOE {1} \
    CONFIG.PCW_NOR_SRAM_CS0_T_PC {1} \
    CONFIG.PCW_NOR_SRAM_CS0_T_RC {11} \
    CONFIG.PCW_NOR_SRAM_CS0_T_TR {1} \
    CONFIG.PCW_NOR_SRAM_CS0_T_WC {11} \
    CONFIG.PCW_NOR_SRAM_CS0_T_WP {1} \
    CONFIG.PCW_NOR_SRAM_CS0_WE_TIME {0} \
    CONFIG.PCW_NOR_SRAM_CS1_T_CEOE {1} \
    CONFIG.PCW_NOR_SRAM_CS1_T_PC {1} \
    CONFIG.PCW_NOR_SRAM_CS1_T_RC {11} \
    CONFIG.PCW_NOR_SRAM_CS1_T_TR {1} \
    CONFIG.PCW_NOR_SRAM_CS1_T_WC {11} \
    CONFIG.PCW_NOR_SRAM_CS1_T_WP {1} \
    CONFIG.PCW_NOR_SRAM_CS1_WE_TIME {0} \
    CONFIG.PCW_OVERRIDE_BASIC_CLOCK {0} \
    CONFIG.PCW_PACKAGE_DDR_BOARD_DELAY0 {0.096} \
    CONFIG.PCW_PACKAGE_DDR_BOARD_DELAY1 {0.102} \
    CONFIG.PCW_PACKAGE_DDR_BOARD_DELAY2 {0.100} \
    CONFIG.PCW_PACKAGE_DDR_BOARD_DELAY3 {0.090} \
    CONFIG.PCW_PACKAGE_DDR_DQS_TO_CLK_DELAY_0 {-0.054} \
    CONFIG.PCW_PACKAGE_DDR_DQS_TO_CLK_DELAY_1 {-0.040} \
    CONFIG.PCW_PACKAGE_DDR_DQS_TO_CLK_DELAY_2 {-0.041} \
    CONFIG.PCW_PACKAGE_DDR_DQS_TO_CLK_DELAY_3 {-0.010} \
    CONFIG.PCW_PACKAGE_NAME {clg485} \
    CONFIG.PCW_PCAP_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_PCAP_PERIPHERAL_FREQMHZ {200} \
    CONFIG.PCW_PERIPHERAL_BOARD_PRESET {None} \
    CONFIG.PCW_PJTAG_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_PLL_BYPASSMODE_ENABLE {0} \
    CONFIG.PCW_PRESET_BANK0_VOLTAGE {LVCMOS 3.3V} \
    CONFIG.PCW_PRESET_BANK1_VOLTAGE {LVCMOS 1.8V} \
    CONFIG.PCW_PS7_SI_REV {PRODUCTION} \
    CONFIG.PCW_QSPI_INTERNAL_HIGHADDRESS {0xFCFFFFFF} \
    CONFIG.PCW_QSPI_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_QSPI_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_SD0_GRP_CD_ENABLE {1} \
    CONFIG.PCW_SD0_GRP_CD_IO {MIO 10} \
    CONFIG.PCW_SD0_GRP_POW_ENABLE {0} \
    CONFIG.PCW_SD0_GRP_WP_ENABLE {0} \
    CONFIG.PCW_SD0_PERIPHERAL_ENABLE {1} \
    CONFIG.PCW_SD0_SD0_IO {MIO 40 .. 45} \
    CONFIG.PCW_SD1_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_SDIO0_BASEADDR {0xE0100000} \
    CONFIG.PCW_SDIO0_HIGHADDR {0xE0100FFF} \
    CONFIG.PCW_SDIO_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_SDIO_PERIPHERAL_FREQMHZ {100} \
    CONFIG.PCW_SDIO_PERIPHERAL_VALID {1} \
    CONFIG.PCW_SMC_CYCLE_T0 {NA} \
    CONFIG.PCW_SMC_CYCLE_T1 {NA} \
    CONFIG.PCW_SMC_CYCLE_T2 {NA} \
    CONFIG.PCW_SMC_CYCLE_T3 {NA} \
    CONFIG.PCW_SMC_CYCLE_T4 {NA} \
    CONFIG.PCW_SMC_CYCLE_T5 {NA} \
    CONFIG.PCW_SMC_CYCLE_T6 {NA} \
    CONFIG.PCW_SMC_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_SMC_PERIPHERAL_VALID {0} \
    CONFIG.PCW_SPI0_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_SPI1_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_SPI_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_SPI_PERIPHERAL_VALID {0} \
    CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} \
    CONFIG.PCW_S_AXI_HP0_ID_WIDTH {6} \
    CONFIG.PCW_S_AXI_HP1_DATA_WIDTH {64} \
    CONFIG.PCW_S_AXI_HP2_DATA_WIDTH {64} \
    CONFIG.PCW_S_AXI_HP2_ID_WIDTH {6} \
    CONFIG.PCW_S_AXI_HP3_DATA_WIDTH {64} \
    CONFIG.PCW_TPIU_PERIPHERAL_CLKSRC {External} \
    CONFIG.PCW_TRACE_INTERNAL_WIDTH {2} \
    CONFIG.PCW_TRACE_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_TTC0_CLK0_PERIPHERAL_CLKSRC {CPU_1X} \
    CONFIG.PCW_TTC0_CLK0_PERIPHERAL_DIVISOR0 {1} \
    CONFIG.PCW_TTC0_CLK1_PERIPHERAL_CLKSRC {CPU_1X} \
    CONFIG.PCW_TTC0_CLK1_PERIPHERAL_DIVISOR0 {1} \
    CONFIG.PCW_TTC0_CLK2_PERIPHERAL_CLKSRC {CPU_1X} \
    CONFIG.PCW_TTC0_CLK2_PERIPHERAL_DIVISOR0 {1} \
    CONFIG.PCW_TTC0_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_TTC1_CLK0_PERIPHERAL_CLKSRC {CPU_1X} \
    CONFIG.PCW_TTC1_CLK0_PERIPHERAL_DIVISOR0 {1} \
    CONFIG.PCW_TTC1_CLK1_PERIPHERAL_CLKSRC {CPU_1X} \
    CONFIG.PCW_TTC1_CLK1_PERIPHERAL_DIVISOR0 {1} \
    CONFIG.PCW_TTC1_CLK2_PERIPHERAL_CLKSRC {CPU_1X} \
    CONFIG.PCW_TTC1_CLK2_PERIPHERAL_DIVISOR0 {1} \
    CONFIG.PCW_TTC1_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_UART0_BASEADDR {0xE0000000} \
    CONFIG.PCW_UART0_BAUD_RATE {115200} \
    CONFIG.PCW_UART0_GRP_FULL_ENABLE {0} \
    CONFIG.PCW_UART0_HIGHADDR {0xE0000FFF} \
    CONFIG.PCW_UART0_PERIPHERAL_ENABLE {1} \
    CONFIG.PCW_UART0_UART0_IO {MIO 14 .. 15} \
    CONFIG.PCW_UART1_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_UART_PERIPHERAL_CLKSRC {IO PLL} \
    CONFIG.PCW_UART_PERIPHERAL_FREQMHZ {100} \
    CONFIG.PCW_UART_PERIPHERAL_VALID {1} \
    CONFIG.PCW_UIPARAM_ACT_DDR_FREQ_MHZ {533.333374} \
    CONFIG.PCW_UIPARAM_DDR_ADV_ENABLE {0} \
    CONFIG.PCW_UIPARAM_DDR_AL {0} \
    CONFIG.PCW_UIPARAM_DDR_BL {8} \
    CONFIG.PCW_UIPARAM_DDR_BOARD_DELAY0 {0.25} \
    CONFIG.PCW_UIPARAM_DDR_BOARD_DELAY1 {0.25} \
    CONFIG.PCW_UIPARAM_DDR_BOARD_DELAY2 {0.25} \
    CONFIG.PCW_UIPARAM_DDR_BOARD_DELAY3 {0.25} \
    CONFIG.PCW_UIPARAM_DDR_BUS_WIDTH {32 Bit} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_0_LENGTH_MM {0} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_0_PACKAGE_LENGTH {80.0515} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_0_PROPOGATION_DELAY {160} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_1_LENGTH_MM {0} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_1_PACKAGE_LENGTH {80.0515} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_1_PROPOGATION_DELAY {160} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_2_LENGTH_MM {0} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_2_PACKAGE_LENGTH {80.0515} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_2_PROPOGATION_DELAY {160} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_3_LENGTH_MM {0} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_3_PACKAGE_LENGTH {80.0515} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_3_PROPOGATION_DELAY {160} \
    CONFIG.PCW_UIPARAM_DDR_CLOCK_STOP_EN {0} \
    CONFIG.PCW_UIPARAM_DDR_DQS_0_LENGTH_MM {0} \
    CONFIG.PCW_UIPARAM_DDR_DQS_0_PACKAGE_LENGTH {133.8645} \
    CONFIG.PCW_UIPARAM_DDR_DQS_0_PROPOGATION_DELAY {160} \
    CONFIG.PCW_UIPARAM_DDR_DQS_1_LENGTH_MM {0} \
    CONFIG.PCW_UIPARAM_DDR_DQS_1_PACKAGE_LENGTH {119.997} \
    CONFIG.PCW_UIPARAM_DDR_DQS_1_PROPOGATION_DELAY {160} \
    CONFIG.PCW_UIPARAM_DDR_DQS_2_LENGTH_MM {0} \
    CONFIG.PCW_UIPARAM_DDR_DQS_2_PACKAGE_LENGTH {121.146} \
    CONFIG.PCW_UIPARAM_DDR_DQS_2_PROPOGATION_DELAY {160} \
    CONFIG.PCW_UIPARAM_DDR_DQS_3_LENGTH_MM {0} \
    CONFIG.PCW_UIPARAM_DDR_DQS_3_PACKAGE_LENGTH {90.125} \
    CONFIG.PCW_UIPARAM_DDR_DQS_3_PROPOGATION_DELAY {160} \
    CONFIG.PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_0 {0.0} \
    CONFIG.PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_1 {0.0} \
    CONFIG.PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_2 {0.0} \
    CONFIG.PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_3 {0.0} \
    CONFIG.PCW_UIPARAM_DDR_DQ_0_LENGTH_MM {0} \
    CONFIG.PCW_UIPARAM_DDR_DQ_0_PACKAGE_LENGTH {111.7605} \
    CONFIG.PCW_UIPARAM_DDR_DQ_0_PROPOGATION_DELAY {160} \
    CONFIG.PCW_UIPARAM_DDR_DQ_1_LENGTH_MM {0} \
    CONFIG.PCW_UIPARAM_DDR_DQ_1_PACKAGE_LENGTH {123.5525} \
    CONFIG.PCW_UIPARAM_DDR_DQ_1_PROPOGATION_DELAY {160} \
    CONFIG.PCW_UIPARAM_DDR_DQ_2_LENGTH_MM {0} \
    CONFIG.PCW_UIPARAM_DDR_DQ_2_PACKAGE_LENGTH {120.714} \
    CONFIG.PCW_UIPARAM_DDR_DQ_2_PROPOGATION_DELAY {160} \
    CONFIG.PCW_UIPARAM_DDR_DQ_3_LENGTH_MM {0} \
    CONFIG.PCW_UIPARAM_DDR_DQ_3_PACKAGE_LENGTH {100.836} \
    CONFIG.PCW_UIPARAM_DDR_DQ_3_PROPOGATION_DELAY {160} \
    CONFIG.PCW_UIPARAM_DDR_ENABLE {1} \
    CONFIG.PCW_UIPARAM_DDR_FREQ_MHZ {533.333333} \
    CONFIG.PCW_UIPARAM_DDR_HIGH_TEMP {Normal (0-85)} \
    CONFIG.PCW_UIPARAM_DDR_MEMORY_TYPE {DDR 3 (Low Voltage)} \
    CONFIG.PCW_UIPARAM_DDR_PARTNO {MT41K256M16 RE-125} \
    CONFIG.PCW_UIPARAM_DDR_TRAIN_DATA_EYE {1} \
    CONFIG.PCW_UIPARAM_DDR_TRAIN_READ_GATE {1} \
    CONFIG.PCW_UIPARAM_DDR_TRAIN_WRITE_LEVEL {1} \
    CONFIG.PCW_UIPARAM_DDR_USE_INTERNAL_VREF {0} \
    CONFIG.PCW_UIPARAM_GENERATE_SUMMARY {NA} \
    CONFIG.PCW_USB0_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_USB1_PERIPHERAL_ENABLE {0} \
    CONFIG.PCW_USB_RESET_POLARITY {Active Low} \
    CONFIG.PCW_USE_AXI_FABRIC_IDLE {0} \
    CONFIG.PCW_USE_AXI_NONSECURE {0} \
    CONFIG.PCW_USE_CORESIGHT {0} \
    CONFIG.PCW_USE_CROSS_TRIGGER {0} \
    CONFIG.PCW_USE_CR_FABRIC {1} \
    CONFIG.PCW_USE_DDR_BYPASS {0} \
    CONFIG.PCW_USE_DEBUG {0} \
    CONFIG.PCW_USE_DMA0 {0} \
    CONFIG.PCW_USE_DMA1 {0} \
    CONFIG.PCW_USE_DMA2 {0} \
    CONFIG.PCW_USE_DMA3 {0} \
    CONFIG.PCW_USE_EXPANDED_IOP {0} \
    CONFIG.PCW_USE_FABRIC_INTERRUPT {0} \
    CONFIG.PCW_USE_HIGH_OCM {0} \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_USE_M_AXI_GP1 {1} \
    CONFIG.PCW_USE_PROC_EVENT_BUS {0} \
    CONFIG.PCW_USE_PS_SLCR_REGISTERS {0} \
    CONFIG.PCW_USE_S_AXI_ACP {0} \
    CONFIG.PCW_USE_S_AXI_GP0 {0} \
    CONFIG.PCW_USE_S_AXI_GP1 {0} \
    CONFIG.PCW_USE_S_AXI_HP0 {1} \
    CONFIG.PCW_USE_S_AXI_HP1 {0} \
    CONFIG.PCW_USE_S_AXI_HP2 {1} \
    CONFIG.PCW_USE_S_AXI_HP3 {0} \
    CONFIG.PCW_USE_TRACE {0} \
    CONFIG.PCW_VALUE_SILVERSION {3} \
    CONFIG.PCW_WDT_PERIPHERAL_CLKSRC {CPU_1X} \
    CONFIG.PCW_WDT_PERIPHERAL_DIVISOR0 {1} \
    CONFIG.PCW_WDT_PERIPHERAL_ENABLE {0} \
    CONFIG.preset {None} \
  ] $processing_system7_0


  # Create instance: ps7_0_axi_periph, and set properties
  set ps7_0_axi_periph [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 ps7_0_axi_periph ]
  set_property -dict [list \
    CONFIG.ENABLE_ADVANCED_OPTIONS {0} \
    CONFIG.ENABLE_PROTOCOL_CHECKERS {0} \
    CONFIG.M00_HAS_DATA_FIFO {0} \
    CONFIG.M00_HAS_REGSLICE {0} \
    CONFIG.M00_ISSUANCE {0} \
    CONFIG.M00_SECURE {0} \
    CONFIG.M01_HAS_DATA_FIFO {0} \
    CONFIG.M01_HAS_REGSLICE {0} \
    CONFIG.M01_ISSUANCE {0} \
    CONFIG.M01_SECURE {0} \
    CONFIG.M02_HAS_DATA_FIFO {0} \
    CONFIG.M02_HAS_REGSLICE {0} \
    CONFIG.M02_ISSUANCE {0} \
    CONFIG.M02_SECURE {0} \
    CONFIG.M03_HAS_DATA_FIFO {0} \
    CONFIG.M03_HAS_REGSLICE {0} \
    CONFIG.M03_ISSUANCE {0} \
    CONFIG.M03_SECURE {0} \
    CONFIG.M04_HAS_DATA_FIFO {0} \
    CONFIG.M04_HAS_REGSLICE {0} \
    CONFIG.M04_ISSUANCE {0} \
    CONFIG.M04_SECURE {0} \
    CONFIG.M05_HAS_DATA_FIFO {0} \
    CONFIG.M05_HAS_REGSLICE {0} \
    CONFIG.M05_ISSUANCE {0} \
    CONFIG.M05_SECURE {0} \
    CONFIG.M06_HAS_DATA_FIFO {0} \
    CONFIG.M06_HAS_REGSLICE {0} \
    CONFIG.M06_ISSUANCE {0} \
    CONFIG.M06_SECURE {0} \
    CONFIG.M07_HAS_DATA_FIFO {0} \
    CONFIG.M07_HAS_REGSLICE {0} \
    CONFIG.M07_ISSUANCE {0} \
    CONFIG.M07_SECURE {0} \
    CONFIG.M08_HAS_DATA_FIFO {0} \
    CONFIG.M08_HAS_REGSLICE {0} \
    CONFIG.M08_ISSUANCE {0} \
    CONFIG.M08_SECURE {0} \
    CONFIG.M09_HAS_DATA_FIFO {0} \
    CONFIG.M09_HAS_REGSLICE {0} \
    CONFIG.M09_ISSUANCE {0} \
    CONFIG.M09_SECURE {0} \
    CONFIG.M10_HAS_DATA_FIFO {0} \
    CONFIG.M10_HAS_REGSLICE {0} \
    CONFIG.M10_ISSUANCE {0} \
    CONFIG.M10_SECURE {0} \
    CONFIG.M11_HAS_DATA_FIFO {0} \
    CONFIG.M11_HAS_REGSLICE {0} \
    CONFIG.M11_ISSUANCE {0} \
    CONFIG.M11_SECURE {0} \
    CONFIG.M12_HAS_DATA_FIFO {0} \
    CONFIG.M12_HAS_REGSLICE {0} \
    CONFIG.M12_ISSUANCE {0} \
    CONFIG.M12_SECURE {0} \
    CONFIG.M13_HAS_DATA_FIFO {0} \
    CONFIG.M13_HAS_REGSLICE {0} \
    CONFIG.M13_ISSUANCE {0} \
    CONFIG.M13_SECURE {0} \
    CONFIG.M14_HAS_DATA_FIFO {0} \
    CONFIG.M14_HAS_REGSLICE {0} \
    CONFIG.M14_ISSUANCE {0} \
    CONFIG.M14_SECURE {0} \
    CONFIG.M15_HAS_DATA_FIFO {0} \
    CONFIG.M15_HAS_REGSLICE {0} \
    CONFIG.M15_ISSUANCE {0} \
    CONFIG.M15_SECURE {0} \
    CONFIG.M16_HAS_DATA_FIFO {0} \
    CONFIG.M16_HAS_REGSLICE {0} \
    CONFIG.M16_ISSUANCE {0} \
    CONFIG.M16_SECURE {0} \
    CONFIG.M17_HAS_DATA_FIFO {0} \
    CONFIG.M17_HAS_REGSLICE {0} \
    CONFIG.M17_ISSUANCE {0} \
    CONFIG.M17_SECURE {0} \
    CONFIG.M18_HAS_DATA_FIFO {0} \
    CONFIG.M18_HAS_REGSLICE {0} \
    CONFIG.M18_ISSUANCE {0} \
    CONFIG.M18_SECURE {0} \
    CONFIG.M19_HAS_DATA_FIFO {0} \
    CONFIG.M19_HAS_REGSLICE {0} \
    CONFIG.M19_ISSUANCE {0} \
    CONFIG.M19_SECURE {0} \
    CONFIG.M20_HAS_DATA_FIFO {0} \
    CONFIG.M20_HAS_REGSLICE {0} \
    CONFIG.M20_ISSUANCE {0} \
    CONFIG.M20_SECURE {0} \
    CONFIG.M21_HAS_DATA_FIFO {0} \
    CONFIG.M21_HAS_REGSLICE {0} \
    CONFIG.M21_ISSUANCE {0} \
    CONFIG.M21_SECURE {0} \
    CONFIG.M22_HAS_DATA_FIFO {0} \
    CONFIG.M22_HAS_REGSLICE {0} \
    CONFIG.M22_ISSUANCE {0} \
    CONFIG.M22_SECURE {0} \
    CONFIG.M23_HAS_DATA_FIFO {0} \
    CONFIG.M23_HAS_REGSLICE {0} \
    CONFIG.M23_ISSUANCE {0} \
    CONFIG.M23_SECURE {0} \
    CONFIG.M24_HAS_DATA_FIFO {0} \
    CONFIG.M24_HAS_REGSLICE {0} \
    CONFIG.M24_ISSUANCE {0} \
    CONFIG.M24_SECURE {0} \
    CONFIG.M25_HAS_DATA_FIFO {0} \
    CONFIG.M25_HAS_REGSLICE {0} \
    CONFIG.M25_ISSUANCE {0} \
    CONFIG.M25_SECURE {0} \
    CONFIG.M26_HAS_DATA_FIFO {0} \
    CONFIG.M26_HAS_REGSLICE {0} \
    CONFIG.M26_ISSUANCE {0} \
    CONFIG.M26_SECURE {0} \
    CONFIG.M27_HAS_DATA_FIFO {0} \
    CONFIG.M27_HAS_REGSLICE {0} \
    CONFIG.M27_ISSUANCE {0} \
    CONFIG.M27_SECURE {0} \
    CONFIG.M28_HAS_DATA_FIFO {0} \
    CONFIG.M28_HAS_REGSLICE {0} \
    CONFIG.M28_ISSUANCE {0} \
    CONFIG.M28_SECURE {0} \
    CONFIG.M29_HAS_DATA_FIFO {0} \
    CONFIG.M29_HAS_REGSLICE {0} \
    CONFIG.M29_ISSUANCE {0} \
    CONFIG.M29_SECURE {0} \
    CONFIG.M30_HAS_DATA_FIFO {0} \
    CONFIG.M30_HAS_REGSLICE {0} \
    CONFIG.M30_ISSUANCE {0} \
    CONFIG.M30_SECURE {0} \
    CONFIG.M31_HAS_DATA_FIFO {0} \
    CONFIG.M31_HAS_REGSLICE {0} \
    CONFIG.M31_ISSUANCE {0} \
    CONFIG.M31_SECURE {0} \
    CONFIG.M32_HAS_DATA_FIFO {0} \
    CONFIG.M32_HAS_REGSLICE {0} \
    CONFIG.M32_ISSUANCE {0} \
    CONFIG.M32_SECURE {0} \
    CONFIG.M33_HAS_DATA_FIFO {0} \
    CONFIG.M33_HAS_REGSLICE {0} \
    CONFIG.M33_ISSUANCE {0} \
    CONFIG.M33_SECURE {0} \
    CONFIG.M34_HAS_DATA_FIFO {0} \
    CONFIG.M34_HAS_REGSLICE {0} \
    CONFIG.M34_ISSUANCE {0} \
    CONFIG.M34_SECURE {0} \
    CONFIG.M35_HAS_DATA_FIFO {0} \
    CONFIG.M35_HAS_REGSLICE {0} \
    CONFIG.M35_ISSUANCE {0} \
    CONFIG.M35_SECURE {0} \
    CONFIG.M36_HAS_DATA_FIFO {0} \
    CONFIG.M36_HAS_REGSLICE {0} \
    CONFIG.M36_ISSUANCE {0} \
    CONFIG.M36_SECURE {0} \
    CONFIG.M37_HAS_DATA_FIFO {0} \
    CONFIG.M37_HAS_REGSLICE {0} \
    CONFIG.M37_ISSUANCE {0} \
    CONFIG.M37_SECURE {0} \
    CONFIG.M38_HAS_DATA_FIFO {0} \
    CONFIG.M38_HAS_REGSLICE {0} \
    CONFIG.M38_ISSUANCE {0} \
    CONFIG.M38_SECURE {0} \
    CONFIG.M39_HAS_DATA_FIFO {0} \
    CONFIG.M39_HAS_REGSLICE {0} \
    CONFIG.M39_ISSUANCE {0} \
    CONFIG.M39_SECURE {0} \
    CONFIG.M40_HAS_DATA_FIFO {0} \
    CONFIG.M40_HAS_REGSLICE {0} \
    CONFIG.M40_ISSUANCE {0} \
    CONFIG.M40_SECURE {0} \
    CONFIG.M41_HAS_DATA_FIFO {0} \
    CONFIG.M41_HAS_REGSLICE {0} \
    CONFIG.M41_ISSUANCE {0} \
    CONFIG.M41_SECURE {0} \
    CONFIG.M42_HAS_DATA_FIFO {0} \
    CONFIG.M42_HAS_REGSLICE {0} \
    CONFIG.M42_ISSUANCE {0} \
    CONFIG.M42_SECURE {0} \
    CONFIG.M43_HAS_DATA_FIFO {0} \
    CONFIG.M43_HAS_REGSLICE {0} \
    CONFIG.M43_ISSUANCE {0} \
    CONFIG.M43_SECURE {0} \
    CONFIG.M44_HAS_DATA_FIFO {0} \
    CONFIG.M44_HAS_REGSLICE {0} \
    CONFIG.M44_ISSUANCE {0} \
    CONFIG.M44_SECURE {0} \
    CONFIG.M45_HAS_DATA_FIFO {0} \
    CONFIG.M45_HAS_REGSLICE {0} \
    CONFIG.M45_ISSUANCE {0} \
    CONFIG.M45_SECURE {0} \
    CONFIG.M46_HAS_DATA_FIFO {0} \
    CONFIG.M46_HAS_REGSLICE {0} \
    CONFIG.M46_ISSUANCE {0} \
    CONFIG.M46_SECURE {0} \
    CONFIG.M47_HAS_DATA_FIFO {0} \
    CONFIG.M47_HAS_REGSLICE {0} \
    CONFIG.M47_ISSUANCE {0} \
    CONFIG.M47_SECURE {0} \
    CONFIG.M48_HAS_DATA_FIFO {0} \
    CONFIG.M48_HAS_REGSLICE {0} \
    CONFIG.M48_ISSUANCE {0} \
    CONFIG.M48_SECURE {0} \
    CONFIG.M49_HAS_DATA_FIFO {0} \
    CONFIG.M49_HAS_REGSLICE {0} \
    CONFIG.M49_ISSUANCE {0} \
    CONFIG.M49_SECURE {0} \
    CONFIG.M50_HAS_DATA_FIFO {0} \
    CONFIG.M50_HAS_REGSLICE {0} \
    CONFIG.M50_ISSUANCE {0} \
    CONFIG.M50_SECURE {0} \
    CONFIG.M51_HAS_DATA_FIFO {0} \
    CONFIG.M51_HAS_REGSLICE {0} \
    CONFIG.M51_ISSUANCE {0} \
    CONFIG.M51_SECURE {0} \
    CONFIG.M52_HAS_DATA_FIFO {0} \
    CONFIG.M52_HAS_REGSLICE {0} \
    CONFIG.M52_ISSUANCE {0} \
    CONFIG.M52_SECURE {0} \
    CONFIG.M53_HAS_DATA_FIFO {0} \
    CONFIG.M53_HAS_REGSLICE {0} \
    CONFIG.M53_ISSUANCE {0} \
    CONFIG.M53_SECURE {0} \
    CONFIG.M54_HAS_DATA_FIFO {0} \
    CONFIG.M54_HAS_REGSLICE {0} \
    CONFIG.M54_ISSUANCE {0} \
    CONFIG.M54_SECURE {0} \
    CONFIG.M55_HAS_DATA_FIFO {0} \
    CONFIG.M55_HAS_REGSLICE {0} \
    CONFIG.M55_ISSUANCE {0} \
    CONFIG.M55_SECURE {0} \
    CONFIG.M56_HAS_DATA_FIFO {0} \
    CONFIG.M56_HAS_REGSLICE {0} \
    CONFIG.M56_ISSUANCE {0} \
    CONFIG.M56_SECURE {0} \
    CONFIG.M57_HAS_DATA_FIFO {0} \
    CONFIG.M57_HAS_REGSLICE {0} \
    CONFIG.M57_ISSUANCE {0} \
    CONFIG.M57_SECURE {0} \
    CONFIG.M58_HAS_DATA_FIFO {0} \
    CONFIG.M58_HAS_REGSLICE {0} \
    CONFIG.M58_ISSUANCE {0} \
    CONFIG.M58_SECURE {0} \
    CONFIG.M59_HAS_DATA_FIFO {0} \
    CONFIG.M59_HAS_REGSLICE {0} \
    CONFIG.M59_ISSUANCE {0} \
    CONFIG.M59_SECURE {0} \
    CONFIG.M60_HAS_DATA_FIFO {0} \
    CONFIG.M60_HAS_REGSLICE {0} \
    CONFIG.M60_ISSUANCE {0} \
    CONFIG.M60_SECURE {0} \
    CONFIG.M61_HAS_DATA_FIFO {0} \
    CONFIG.M61_HAS_REGSLICE {0} \
    CONFIG.M61_ISSUANCE {0} \
    CONFIG.M61_SECURE {0} \
    CONFIG.M62_HAS_DATA_FIFO {0} \
    CONFIG.M62_HAS_REGSLICE {0} \
    CONFIG.M62_ISSUANCE {0} \
    CONFIG.M62_SECURE {0} \
    CONFIG.M63_HAS_DATA_FIFO {0} \
    CONFIG.M63_HAS_REGSLICE {0} \
    CONFIG.M63_ISSUANCE {0} \
    CONFIG.M63_SECURE {0} \
    CONFIG.NUM_MI {8} \
    CONFIG.NUM_SI {1} \
    CONFIG.PCHK_MAX_RD_BURSTS {2} \
    CONFIG.PCHK_MAX_WR_BURSTS {2} \
    CONFIG.PCHK_WAITS {0} \
    CONFIG.S00_ARB_PRIORITY {0} \
    CONFIG.S00_HAS_DATA_FIFO {0} \
    CONFIG.S00_HAS_REGSLICE {0} \
    CONFIG.S01_ARB_PRIORITY {0} \
    CONFIG.S01_HAS_DATA_FIFO {0} \
    CONFIG.S01_HAS_REGSLICE {0} \
    CONFIG.S02_ARB_PRIORITY {0} \
    CONFIG.S02_HAS_DATA_FIFO {0} \
    CONFIG.S02_HAS_REGSLICE {0} \
    CONFIG.S03_ARB_PRIORITY {0} \
    CONFIG.S03_HAS_DATA_FIFO {0} \
    CONFIG.S03_HAS_REGSLICE {0} \
    CONFIG.S04_ARB_PRIORITY {0} \
    CONFIG.S04_HAS_DATA_FIFO {0} \
    CONFIG.S04_HAS_REGSLICE {0} \
    CONFIG.S05_ARB_PRIORITY {0} \
    CONFIG.S05_HAS_DATA_FIFO {0} \
    CONFIG.S05_HAS_REGSLICE {0} \
    CONFIG.S06_ARB_PRIORITY {0} \
    CONFIG.S06_HAS_DATA_FIFO {0} \
    CONFIG.S06_HAS_REGSLICE {0} \
    CONFIG.S07_ARB_PRIORITY {0} \
    CONFIG.S07_HAS_DATA_FIFO {0} \
    CONFIG.S07_HAS_REGSLICE {0} \
    CONFIG.S08_ARB_PRIORITY {0} \
    CONFIG.S08_HAS_DATA_FIFO {0} \
    CONFIG.S08_HAS_REGSLICE {0} \
    CONFIG.S09_ARB_PRIORITY {0} \
    CONFIG.S09_HAS_DATA_FIFO {0} \
    CONFIG.S09_HAS_REGSLICE {0} \
    CONFIG.S10_ARB_PRIORITY {0} \
    CONFIG.S10_HAS_DATA_FIFO {0} \
    CONFIG.S10_HAS_REGSLICE {0} \
    CONFIG.S11_ARB_PRIORITY {0} \
    CONFIG.S11_HAS_DATA_FIFO {0} \
    CONFIG.S11_HAS_REGSLICE {0} \
    CONFIG.S12_ARB_PRIORITY {0} \
    CONFIG.S12_HAS_DATA_FIFO {0} \
    CONFIG.S12_HAS_REGSLICE {0} \
    CONFIG.S13_ARB_PRIORITY {0} \
    CONFIG.S13_HAS_DATA_FIFO {0} \
    CONFIG.S13_HAS_REGSLICE {0} \
    CONFIG.S14_ARB_PRIORITY {0} \
    CONFIG.S14_HAS_DATA_FIFO {0} \
    CONFIG.S14_HAS_REGSLICE {0} \
    CONFIG.S15_ARB_PRIORITY {0} \
    CONFIG.S15_HAS_DATA_FIFO {0} \
    CONFIG.S15_HAS_REGSLICE {0} \
    CONFIG.STRATEGY {0} \
    CONFIG.SYNCHRONIZATION_STAGES {3} \
    CONFIG.XBAR_DATA_WIDTH {32} \
  ] $ps7_0_axi_periph


  # Create instance: rst_ps7_0_100M, and set properties
  set rst_ps7_0_100M [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps7_0_100M ]
  set_property -dict [list \
    CONFIG.C_AUX_RESET_HIGH {0} \
    CONFIG.C_AUX_RST_WIDTH {4} \
    CONFIG.C_EXT_RST_WIDTH {4} \
    CONFIG.C_NUM_BUS_RST {1} \
    CONFIG.C_NUM_INTERCONNECT_ARESETN {1} \
    CONFIG.C_NUM_PERP_ARESETN {1} \
    CONFIG.C_NUM_PERP_RST {1} \
    CONFIG.RESET_BOARD_INTERFACE {Custom} \
    CONFIG.USE_BOARD_FLOW {false} \
  ] $rst_ps7_0_100M


  # Create instance: rst_ps7_0_150M, and set properties
  set rst_ps7_0_150M [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps7_0_150M ]
  set_property -dict [list \
    CONFIG.C_AUX_RESET_HIGH {0} \
    CONFIG.C_AUX_RST_WIDTH {4} \
    CONFIG.C_EXT_RST_WIDTH {4} \
    CONFIG.C_NUM_BUS_RST {1} \
    CONFIG.C_NUM_INTERCONNECT_ARESETN {1} \
    CONFIG.C_NUM_PERP_ARESETN {1} \
    CONFIG.C_NUM_PERP_RST {1} \
    CONFIG.RESET_BOARD_INTERFACE {Custom} \
    CONFIG.USE_BOARD_FLOW {false} \
  ] $rst_ps7_0_150M


  # Create instance: util_vector_logic_0, and set properties
  set util_vector_logic_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:util_vector_logic:2.0 util_vector_logic_0 ]
  set_property -dict [list \
    CONFIG.C_OPERATION {not} \
    CONFIG.C_SIZE {1} \
  ] $util_vector_logic_0


  # Create instance: v_axi4s_vid_out_0, and set properties
  set v_axi4s_vid_out_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:v_axi4s_vid_out:4.0 v_axi4s_vid_out_0 ]
  set_property -dict [list \
    CONFIG.ARBITRARY_RES_EN {false} \
    CONFIG.C_ADDR_WIDTH {10} \
    CONFIG.C_ADDR_WIDTH_PIXEL_REMAP_420 {10} \
    CONFIG.C_HAS_ASYNC_CLK {1} \
    CONFIG.C_HYSTERESIS_LEVEL {12} \
    CONFIG.C_INCLUDE_PIXEL_REMAP_420 {0} \
    CONFIG.C_INCLUDE_PIXEL_REPEAT {0} \
    CONFIG.C_NATIVE_COMPONENT_WIDTH {8} \
    CONFIG.C_PIXELS_PER_CLOCK {1} \
    CONFIG.C_SYNC_LOCK_THRESHOLD {4} \
    CONFIG.C_S_AXIS_VIDEO_DATA_WIDTH {8} \
    CONFIG.C_S_AXIS_VIDEO_FORMAT {2} \
    CONFIG.C_VTG_MASTER_SLAVE {0} \
  ] $v_axi4s_vid_out_0


  # Create instance: v_tc_0, and set properties
  set v_tc_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:v_tc:6.2 v_tc_0 ]
  set_property -dict [list \
    CONFIG.ARBITRARY_RES_EN {false} \
    CONFIG.C_FAMILY {virtex7} \
    CONFIG.FSYNC_HSTART0 {0} \
    CONFIG.FSYNC_VSTART0 {0} \
    CONFIG.GEN_AVIDEO_POLARITY {High} \
    CONFIG.GEN_CPARITY {0} \
    CONFIG.GEN_HBLANK_POLARITY {High} \
    CONFIG.GEN_HSYNC_POLARITY {High} \
    CONFIG.GEN_VBLANK_POLARITY {High} \
    CONFIG.GEN_VIDEO_FORMAT {RGB} \
    CONFIG.GEN_VSYNC_POLARITY {High} \
    CONFIG.HAS_AXI4_LITE {true} \
    CONFIG.HAS_INTC_IF {false} \
    CONFIG.INTERLACE_EN {false} \
    CONFIG.SYNC_EN {false} \
    CONFIG.VIDEO_MODE {720p} \
    CONFIG.active_chroma_generation {false} \
    CONFIG.active_video_generation {true} \
    CONFIG.enable_detection {false} \
    CONFIG.enable_generation {true} \
    CONFIG.frame_syncs {1} \
    CONFIG.horizontal_blank_generation {true} \
    CONFIG.horizontal_sync_generation {true} \
    CONFIG.max_clocks_per_line {4096} \
    CONFIG.max_lines_per_frame {4096} \
    CONFIG.vertical_blank_generation {true} \
    CONFIG.vertical_sync_generation {true} \
  ] $v_tc_0


  # Create instance: v_vid_in_axi4s_0, and set properties
  set v_vid_in_axi4s_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:v_vid_in_axi4s:5.0 v_vid_in_axi4s_0 ]
  set_property -dict [list \
    CONFIG.C_ADDR_WIDTH {10} \
    CONFIG.C_ADDR_WIDTH_PIXEL_REMAP_420 {10} \
    CONFIG.C_HAS_ASYNC_CLK {1} \
    CONFIG.C_INCLUDE_PIXEL_DROP {0} \
    CONFIG.C_INCLUDE_PIXEL_REMAP_420 {0} \
    CONFIG.C_M_AXIS_VIDEO_DATA_WIDTH {8} \
    CONFIG.C_M_AXIS_VIDEO_FORMAT {2} \
    CONFIG.C_NATIVE_COMPONENT_WIDTH {8} \
    CONFIG.C_PIXELS_PER_CLOCK {1} \
    CONFIG.C_VID_NATIVE_DE {0} \
  ] $v_vid_in_axi4s_0


  # Create instance: v_vid_snapshot, and set properties
  set v_vid_snapshot [ create_bd_cell -type ip -vlnv xilinx.com:ip:v_vid_in_axi4s:5.0 v_vid_snapshot ]
  set_property -dict [list \
    CONFIG.C_ADDR_WIDTH {10} \
    CONFIG.C_ADDR_WIDTH_PIXEL_REMAP_420 {10} \
    CONFIG.C_HAS_ASYNC_CLK {1} \
    CONFIG.C_INCLUDE_PIXEL_DROP {0} \
    CONFIG.C_INCLUDE_PIXEL_REMAP_420 {0} \
    CONFIG.C_M_AXIS_VIDEO_DATA_WIDTH {8} \
    CONFIG.C_M_AXIS_VIDEO_FORMAT {2} \
    CONFIG.C_NATIVE_COMPONENT_WIDTH {8} \
    CONFIG.C_PIXELS_PER_CLOCK {1} \
    CONFIG.C_VID_NATIVE_DE {0} \
  ] $v_vid_snapshot


  # Create instance: hdmi_audio_tx_0, and set properties
  set block_name hdmi_audio_tx
  set block_cell_name hdmi_audio_tx_0
  if { [catch {set hdmi_audio_tx_0 [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $hdmi_audio_tx_0 eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: audio_sample_tick_0, and set properties
  set block_name audio_sample_tick
  set block_cell_name audio_sample_tick_0
  if { [catch {set audio_sample_tick_0 [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $audio_sample_tick_0 eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: pcm_buffer_0, and set properties
  set block_name pcm_buffer
  set block_cell_name pcm_buffer_0
  if { [catch {set pcm_buffer_0 [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $pcm_buffer_0 eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
    set_property CONFIG.USE_SAMPLE_ENABLE {1} $pcm_buffer_0


  # Create instance: rst_pixel, and set properties
  set rst_pixel [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_pixel ]

  # Create instance: vision_core_0, and set properties
  set block_name vision_stream_control
  set block_cell_name vision_core_0
  if { [catch {set vision_core_0 [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $vision_core_0 eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: vision_keys_0, and set properties
  set vision_keys_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 vision_keys_0 ]
  set_property -dict [list \
    CONFIG.C_ALL_INPUTS {1} \
    CONFIG.C_GPIO_WIDTH {2} \
    CONFIG.C_IS_DUAL {0} \
  ] $vision_keys_0


  # Create instance: key_inputs_0, and set properties
  set block_name key_inputs
  set block_cell_name key_inputs_0
  if { [catch {set key_inputs_0 [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $key_inputs_0 eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: audio_fft_0, and set properties
  set audio_fft_0 [ create_bd_cell -type ip -vlnv xilinx.com:hls:audio_fft:1.0 audio_fft_0 ]

  # Create instance: z15_fbcsp_0, and set properties
  set z15_fbcsp_0 [ create_bd_cell -type ip -vlnv xilinx.com:hls:z15_fbcsp:1.0 z15_fbcsp_0 ]

  # Create instance: pl_accel_reset, and set properties
  set pl_accel_reset [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 pl_accel_reset ]

  # Create instance: pl_accel_one, and set properties
  set pl_accel_one [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 pl_accel_one ]

  # Create instance: pl_accel_zero, and set properties
  set pl_accel_zero [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 pl_accel_zero ]
  set_property CONFIG.CONST_VAL {0} $pl_accel_zero


  # Create instance: pl_accel_control, and set properties
  set pl_accel_control [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 pl_accel_control ]

  # Create instance: pl_accel_memory, and set properties
  set pl_accel_memory [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 pl_accel_memory ]
  set_property -dict [list \
    CONFIG.NUM_MI {1} \
    CONFIG.NUM_SI {2} \
  ] $pl_accel_memory


  # Create interface connections
  connect_bd_intf_net -intf_net S00_AXI_1 [get_bd_intf_pins axi_mem_intercon/S00_AXI] [get_bd_intf_pins axi_vdma_0/M_AXI_MM2S]
  connect_bd_intf_net -intf_net S01_AXI_1 [get_bd_intf_pins axi_mem_intercon/S01_AXI] [get_bd_intf_pins axi_vdma_0/M_AXI_S2MM]
  connect_bd_intf_net -intf_net S02_AXI_1 [get_bd_intf_pins axi_mem_intercon/S02_AXI] [get_bd_intf_pins axi_vdma_1/M_AXI_S2MM]
  connect_bd_intf_net -intf_net axi_mem_intercon_M00_AXI [get_bd_intf_pins axi_mem_intercon/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP0]
  connect_bd_intf_net -intf_net axi_vdma_0_M_AXIS_MM2S [get_bd_intf_pins axi_vdma_0/M_AXIS_MM2S] [get_bd_intf_pins v_axi4s_vid_out_0/video_in]
  connect_bd_intf_net -intf_net pl_accel_control_M00_AXI [get_bd_intf_pins pl_accel_control/M00_AXI] [get_bd_intf_pins z15_fbcsp_0/s_axi_control]
  connect_bd_intf_net -intf_net pl_accel_memory_M00_AXI [get_bd_intf_pins pl_accel_memory/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP2]
  connect_bd_intf_net -intf_net processing_system7_0_DDR [get_bd_intf_ports DDR] [get_bd_intf_pins processing_system7_0/DDR]
  connect_bd_intf_net -intf_net processing_system7_0_FIXED_IO [get_bd_intf_ports FIXED_IO] [get_bd_intf_pins processing_system7_0/FIXED_IO]
  connect_bd_intf_net -intf_net processing_system7_0_GPIO_0 [get_bd_intf_ports emio_sccb] [get_bd_intf_pins processing_system7_0/GPIO_0]
  connect_bd_intf_net -intf_net processing_system7_0_M_AXI_GP0 [get_bd_intf_pins processing_system7_0/M_AXI_GP0] [get_bd_intf_pins ps7_0_axi_periph/S00_AXI]
  connect_bd_intf_net -intf_net processing_system7_0_M_AXI_GP1 [get_bd_intf_pins processing_system7_0/M_AXI_GP1] [get_bd_intf_pins pl_accel_control/S00_AXI]
  connect_bd_intf_net -intf_net ps7_0_axi_periph_M00_AXI [get_bd_intf_pins axi_vdma_0/S_AXI_LITE] [get_bd_intf_pins ps7_0_axi_periph/M00_AXI]
  connect_bd_intf_net -intf_net ps7_0_axi_periph_M01_AXI [get_bd_intf_pins ps7_0_axi_periph/M01_AXI] [get_bd_intf_pins v_tc_0/ctrl]
  connect_bd_intf_net -intf_net ps7_0_axi_periph_M02_AXI [get_bd_intf_pins axi_vdma_1/S_AXI_LITE] [get_bd_intf_pins ps7_0_axi_periph/M02_AXI]
  connect_bd_intf_net -intf_net ps7_0_axi_periph_M03_AXI [get_bd_intf_pins live_osd_0/s_axi] [get_bd_intf_pins ps7_0_axi_periph/M03_AXI]
  connect_bd_intf_net -intf_net ps7_0_axi_periph_M04_AXI [get_bd_intf_pins ps7_0_axi_periph/M04_AXI] [get_bd_intf_pins pcm_buffer_0/s_axi]
  connect_bd_intf_net -intf_net ps7_0_axi_periph_M05_AXI [get_bd_intf_pins ps7_0_axi_periph/M05_AXI] [get_bd_intf_pins vision_core_0/s_axi]
  connect_bd_intf_net -intf_net ps7_0_axi_periph_M06_AXI [get_bd_intf_pins ps7_0_axi_periph/M06_AXI] [get_bd_intf_pins vision_keys_0/S_AXI]
  connect_bd_intf_net -intf_net ps7_0_axi_periph_M07_AXI [get_bd_intf_pins ps7_0_axi_periph/M07_AXI] [get_bd_intf_pins audio_fft_0/s_axi_control]
  connect_bd_intf_net -intf_net v_tc_0_vtiming_out [get_bd_intf_pins v_axi4s_vid_out_0/vtiming_in] [get_bd_intf_pins v_tc_0/vtiming_out]
  connect_bd_intf_net -intf_net v_vid_in_axi4s_0_video_out [get_bd_intf_pins axi_vdma_0/S_AXIS_S2MM] [get_bd_intf_pins v_vid_in_axi4s_0/video_out]
  connect_bd_intf_net -intf_net v_vid_snapshot_video_out [get_bd_intf_pins axi_vdma_1/S_AXIS_S2MM] [get_bd_intf_pins v_vid_snapshot/video_out]
  connect_bd_intf_net -intf_net z15_fbcsp_0_m_axi_data [get_bd_intf_pins z15_fbcsp_0/m_axi_data] [get_bd_intf_pins pl_accel_memory/S00_AXI]
  connect_bd_intf_net -intf_net z15_fbcsp_0_m_axi_model [get_bd_intf_pins z15_fbcsp_0/m_axi_model] [get_bd_intf_pins pl_accel_memory/S01_AXI]

  # Create port connections
  connect_bd_net -net ACLK_1 [get_bd_pins processing_system7_0/FCLK_CLK1] [get_bd_pins axi_mem_intercon/ACLK] [get_bd_pins axi_mem_intercon/S00_ACLK] [get_bd_pins axi_mem_intercon/M00_ACLK] [get_bd_pins axi_vdma_0/m_axi_mm2s_aclk] [get_bd_pins axi_vdma_0/m_axis_mm2s_aclk] [get_bd_pins processing_system7_0/S_AXI_HP0_ACLK] [get_bd_pins rst_ps7_0_150M/slowest_sync_clk] [get_bd_pins v_axi4s_vid_out_0/aclk]
  connect_bd_net -net ARESETN_1 [get_bd_pins rst_ps7_0_150M/peripheral_aresetn] [get_bd_pins axi_mem_intercon/ARESETN] [get_bd_pins axi_mem_intercon/S00_ARESETN] [get_bd_pins axi_mem_intercon/M00_ARESETN]
  connect_bd_net -net S01_ACLK_1 [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins axi_mem_intercon/S01_ACLK] [get_bd_pins axi_mem_intercon/S02_ACLK] [get_bd_pins axi_vdma_0/s_axi_lite_aclk] [get_bd_pins axi_vdma_0/m_axi_s2mm_aclk] [get_bd_pins axi_vdma_0/s_axis_s2mm_aclk] [get_bd_pins axi_vdma_1/s_axi_lite_aclk] [get_bd_pins axi_vdma_1/m_axi_s2mm_aclk] [get_bd_pins axi_vdma_1/s_axis_s2mm_aclk] [get_bd_pins clk_wiz_0/clk_in1] [get_bd_pins live_osd_0/aclk] [get_bd_pins processing_system7_0/M_AXI_GP0_ACLK] [get_bd_pins ps7_0_axi_periph/ACLK] [get_bd_pins ps7_0_axi_periph/S00_ACLK] [get_bd_pins ps7_0_axi_periph/M00_ACLK] [get_bd_pins ps7_0_axi_periph/M01_ACLK] [get_bd_pins ps7_0_axi_periph/M02_ACLK] [get_bd_pins ps7_0_axi_periph/M03_ACLK] [get_bd_pins rst_ps7_0_100M/slowest_sync_clk] [get_bd_pins v_tc_0/s_axi_aclk] [get_bd_pins v_vid_in_axi4s_0/aclk] [get_bd_pins v_vid_snapshot/aclk] [get_bd_pins ps7_0_axi_periph/M04_ACLK] [get_bd_pins pcm_buffer_0/s_axi_aclk] [get_bd_pins vision_core_0/aclk] [get_bd_pins vision_keys_0/s_axi_aclk] [get_bd_pins key_inputs_0/aclk] [get_bd_pins ps7_0_axi_periph/M05_ACLK] [get_bd_pins ps7_0_axi_periph/M06_ACLK] [get_bd_pins audio_fft_0/ap_clk] [get_bd_pins ps7_0_axi_periph/M07_ACLK]
  connect_bd_net -net S01_ARESETN_1 [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins axi_mem_intercon/S01_ARESETN] [get_bd_pins axi_mem_intercon/S02_ARESETN] [get_bd_pins axi_vdma_0/axi_resetn] [get_bd_pins axi_vdma_1/axi_resetn] [get_bd_pins live_osd_0/aresetn] [get_bd_pins ps7_0_axi_periph/ARESETN] [get_bd_pins ps7_0_axi_periph/S00_ARESETN] [get_bd_pins ps7_0_axi_periph/M00_ARESETN] [get_bd_pins ps7_0_axi_periph/M01_ARESETN] [get_bd_pins ps7_0_axi_periph/M02_ARESETN] [get_bd_pins ps7_0_axi_periph/M03_ARESETN] [get_bd_pins v_tc_0/s_axi_aresetn] [get_bd_pins ps7_0_axi_periph/M04_ARESETN] [get_bd_pins pcm_buffer_0/s_axi_aresetn] [get_bd_pins vision_core_0/aresetn] [get_bd_pins vision_keys_0/s_axi_aresetn] [get_bd_pins key_inputs_0/aresetn] [get_bd_pins ps7_0_axi_periph/M05_ARESETN] [get_bd_pins ps7_0_axi_periph/M06_ARESETN] [get_bd_pins audio_fft_0/ap_rst_n] [get_bd_pins ps7_0_axi_periph/M07_ARESETN]
  connect_bd_net -net audio_sample_tick_0_sample_enable [get_bd_pins audio_sample_tick_0/sample_enable] [get_bd_pins pcm_buffer_0/sample_enable] [get_bd_pins hdmi_audio_tx_0/sample_enable]
  connect_bd_net -net cam_data_1 [get_bd_ports cam_data] [get_bd_pins ov5640_capture_data_0/cam_data]
  connect_bd_net -net cam_href_1 [get_bd_ports cam_href] [get_bd_pins ov5640_capture_data_0/cam_href]
  connect_bd_net -net cam_pclk_1 [get_bd_ports cam_pclk] [get_bd_pins ov5640_capture_data_0/cam_pclk]
  connect_bd_net -net cam_vsync_1 [get_bd_ports cam_vsync] [get_bd_pins ov5640_capture_data_0/cam_vsync]
  connect_bd_net -net clk_wiz_0_clk_out1 [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins hdmi_audio_tx_0/clk_pixel] [get_bd_pins live_osd_0/pix_clk] [get_bd_pins v_axi4s_vid_out_0/vid_io_out_clk] [get_bd_pins v_tc_0/clk] [get_bd_pins rst_pixel/slowest_sync_clk] [get_bd_pins audio_sample_tick_0/clk_pixel] [get_bd_pins pcm_buffer_0/sample_clk] [get_bd_pins vision_core_0/pix_clk]
  connect_bd_net -net clk_wiz_0_clk_out2 [get_bd_pins clk_wiz_0/clk_out2] [get_bd_pins hdmi_audio_tx_0/clk_pixel_x5]
  connect_bd_net -net clk_wiz_0_locked [get_bd_pins clk_wiz_0/locked] [get_bd_pins ov5640_capture_data_0/rst_n] [get_bd_pins util_vector_logic_0/Op1] [get_bd_pins v_vid_in_axi4s_0/aresetn] [get_bd_pins v_vid_snapshot/aresetn] [get_bd_pins rst_pixel/dcm_locked]
  connect_bd_net -net hdmi_audio_tx_0_tmds_clk_n [get_bd_pins hdmi_audio_tx_0/tmds_clk_n] [get_bd_ports TMDS_0_tmds_clk_n]
  connect_bd_net -net hdmi_audio_tx_0_tmds_clk_p [get_bd_pins hdmi_audio_tx_0/tmds_clk_p] [get_bd_ports TMDS_0_tmds_clk_p]
  connect_bd_net -net hdmi_audio_tx_0_tmds_data_n [get_bd_pins hdmi_audio_tx_0/tmds_data_n] [get_bd_ports TMDS_0_tmds_data_n]
  connect_bd_net -net hdmi_audio_tx_0_tmds_data_p [get_bd_pins hdmi_audio_tx_0/tmds_data_p] [get_bd_ports TMDS_0_tmds_data_p]
  connect_bd_net -net key_inputs_0_value [get_bd_pins key_inputs_0/value] [get_bd_pins vision_keys_0/gpio_io_i]
  connect_bd_net -net live_osd_0_out_data [get_bd_pins live_osd_0/out_data] [get_bd_pins hdmi_audio_tx_0/rgb]
  connect_bd_net -net live_osd_0_out_de [get_bd_pins live_osd_0/out_de] [get_bd_pins hdmi_audio_tx_0/de]
  connect_bd_net -net live_osd_0_out_hsync [get_bd_pins live_osd_0/out_hsync] [get_bd_pins hdmi_audio_tx_0/hsync]
  connect_bd_net -net live_osd_0_out_vsync [get_bd_pins live_osd_0/out_vsync] [get_bd_pins hdmi_audio_tx_0/vsync]
  connect_bd_net -net ov5640_capture_data_0_cam_pwdn [get_bd_pins ov5640_capture_data_0/cam_pwdn] [get_bd_ports cam_pwdn]
  connect_bd_net -net ov5640_capture_data_0_cam_rst_n [get_bd_pins ov5640_capture_data_0/cam_rst_n] [get_bd_ports cam_rst_n]
  connect_bd_net -net ov5640_capture_data_0_cmos_active_video [get_bd_pins ov5640_capture_data_0/cmos_active_video] [get_bd_pins v_vid_in_axi4s_0/vid_active_video] [get_bd_pins v_vid_snapshot/vid_active_video]
  connect_bd_net -net ov5640_capture_data_0_cmos_frame_ce [get_bd_pins ov5640_capture_data_0/cmos_frame_ce] [get_bd_pins v_vid_in_axi4s_0/vid_io_in_ce] [get_bd_pins v_vid_snapshot/vid_io_in_ce]
  connect_bd_net -net ov5640_capture_data_0_cmos_frame_clk [get_bd_pins ov5640_capture_data_0/cmos_frame_clk] [get_bd_pins v_vid_in_axi4s_0/vid_io_in_clk] [get_bd_pins v_vid_snapshot/vid_io_in_clk] [get_bd_pins vision_core_0/cam_clk]
  connect_bd_net -net ov5640_capture_data_0_cmos_frame_data [get_bd_pins ov5640_capture_data_0/cmos_frame_data] [get_bd_pins v_vid_in_axi4s_0/vid_data] [get_bd_pins v_vid_snapshot/vid_data]
  connect_bd_net -net ov5640_capture_data_0_cmos_frame_vsync [get_bd_pins ov5640_capture_data_0/cmos_frame_vsync] [get_bd_pins live_osd_0/cam_vsync] [get_bd_pins v_vid_in_axi4s_0/vid_vsync] [get_bd_pins v_vid_snapshot/vid_vsync] [get_bd_pins vision_core_0/cam_vsync]
  connect_bd_net -net pcm_buffer_0_sample_left [get_bd_pins pcm_buffer_0/sample_left] [get_bd_pins hdmi_audio_tx_0/sample_left]
  connect_bd_net -net pcm_buffer_0_sample_right [get_bd_pins pcm_buffer_0/sample_right] [get_bd_pins hdmi_audio_tx_0/sample_right]
  connect_bd_net -net pl_accel_one_dout [get_bd_pins pl_accel_one/dout] [get_bd_pins pl_accel_reset/dcm_locked]
  connect_bd_net -net pl_accel_reset_peripheral_aresetn [get_bd_pins pl_accel_reset/peripheral_aresetn] [get_bd_pins z15_fbcsp_0/ap_rst_n] [get_bd_pins pl_accel_control/ARESETN] [get_bd_pins pl_accel_control/M00_ARESETN] [get_bd_pins pl_accel_control/M01_ARESETN] [get_bd_pins pl_accel_control/S00_ARESETN] [get_bd_pins pl_accel_memory/ARESETN] [get_bd_pins pl_accel_memory/M00_ARESETN] [get_bd_pins pl_accel_memory/S00_ARESETN] [get_bd_pins pl_accel_memory/S01_ARESETN]
  connect_bd_net -net pl_accel_zero_dout [get_bd_pins pl_accel_zero/dout] [get_bd_pins pl_accel_reset/aux_reset_in] [get_bd_pins pl_accel_reset/mb_debug_sys_rst]
  connect_bd_net -net pl_keys_1 [get_bd_ports pl_keys] [get_bd_pins key_inputs_0/keys]
  connect_bd_net -net processing_system7_0_FCLK_CLK2 [get_bd_pins processing_system7_0/FCLK_CLK2] [get_bd_pins processing_system7_0/M_AXI_GP1_ACLK] [get_bd_pins processing_system7_0/S_AXI_HP2_ACLK] [get_bd_pins z15_fbcsp_0/ap_clk] [get_bd_pins pl_accel_reset/slowest_sync_clk] [get_bd_pins pl_accel_control/ACLK] [get_bd_pins pl_accel_control/M00_ACLK] [get_bd_pins pl_accel_control/M01_ACLK] [get_bd_pins pl_accel_control/S00_ACLK] [get_bd_pins pl_accel_memory/ACLK] [get_bd_pins pl_accel_memory/M00_ACLK] [get_bd_pins pl_accel_memory/S00_ACLK] [get_bd_pins pl_accel_memory/S01_ACLK]
  connect_bd_net -net processing_system7_0_FCLK_RESET0_N [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins rst_ps7_0_100M/ext_reset_in] [get_bd_pins rst_ps7_0_150M/ext_reset_in] [get_bd_pins rst_pixel/ext_reset_in]
  connect_bd_net -net processing_system7_0_FCLK_RESET2_N [get_bd_pins processing_system7_0/FCLK_RESET2_N] [get_bd_pins pl_accel_reset/ext_reset_in]
  connect_bd_net -net rst_pixel_peripheral_reset [get_bd_pins rst_pixel/peripheral_reset] [get_bd_pins hdmi_audio_tx_0/reset] [get_bd_pins audio_sample_tick_0/reset]
  connect_bd_net -net rst_ps7_0_100M_peripheral_reset [get_bd_pins rst_ps7_0_100M/peripheral_reset] [get_bd_pins clk_wiz_0/reset]
  connect_bd_net -net util_vector_logic_0_Res [get_bd_pins util_vector_logic_0/Res] [get_bd_pins v_vid_in_axi4s_0/vid_io_in_reset] [get_bd_pins v_vid_snapshot/vid_io_in_reset]
  connect_bd_net -net v_axi4s_vid_out_0_vid_active_video [get_bd_pins v_axi4s_vid_out_0/vid_active_video] [get_bd_pins vision_core_0/in_de]
  connect_bd_net -net v_axi4s_vid_out_0_vid_data [get_bd_pins v_axi4s_vid_out_0/vid_data] [get_bd_pins vision_core_0/in_data]
  connect_bd_net -net v_axi4s_vid_out_0_vid_field_id [get_bd_pins v_axi4s_vid_out_0/vid_field_id] [get_bd_pins vision_core_0/in_field]
  connect_bd_net -net v_axi4s_vid_out_0_vid_hblank [get_bd_pins v_axi4s_vid_out_0/vid_hblank] [get_bd_pins vision_core_0/in_hblank]
  connect_bd_net -net v_axi4s_vid_out_0_vid_hsync [get_bd_pins v_axi4s_vid_out_0/vid_hsync] [get_bd_pins vision_core_0/in_hsync]
  connect_bd_net -net v_axi4s_vid_out_0_vid_vblank [get_bd_pins v_axi4s_vid_out_0/vid_vblank] [get_bd_pins vision_core_0/in_vblank]
  connect_bd_net -net v_axi4s_vid_out_0_vid_vsync [get_bd_pins v_axi4s_vid_out_0/vid_vsync] [get_bd_pins vision_core_0/in_vsync]
  connect_bd_net -net v_axi4s_vid_out_0_vtg_ce [get_bd_pins v_axi4s_vid_out_0/vtg_ce] [get_bd_pins v_tc_0/gen_clken]
  connect_bd_net -net vision_core_0_out_data [get_bd_pins vision_core_0/out_data] [get_bd_pins live_osd_0/in_data]
  connect_bd_net -net vision_core_0_out_de [get_bd_pins vision_core_0/out_de] [get_bd_pins live_osd_0/in_de]
  connect_bd_net -net vision_core_0_out_field [get_bd_pins vision_core_0/out_field] [get_bd_pins live_osd_0/in_field]
  connect_bd_net -net vision_core_0_out_hblank [get_bd_pins vision_core_0/out_hblank] [get_bd_pins live_osd_0/in_hblank]
  connect_bd_net -net vision_core_0_out_hsync [get_bd_pins vision_core_0/out_hsync] [get_bd_pins live_osd_0/in_hsync]
  connect_bd_net -net vision_core_0_out_vblank [get_bd_pins vision_core_0/out_vblank] [get_bd_pins live_osd_0/in_vblank]
  connect_bd_net -net vision_core_0_out_vsync [get_bd_pins vision_core_0/out_vsync] [get_bd_pins live_osd_0/in_vsync]

  # Create address segments
  assign_bd_address -offset 0x00000000 -range 0x40000000 -target_address_space [get_bd_addr_spaces axi_vdma_0/Data_MM2S] [get_bd_addr_segs processing_system7_0/S_AXI_HP0/HP0_DDR_LOWOCM] -force
  assign_bd_address -offset 0x00000000 -range 0x40000000 -target_address_space [get_bd_addr_spaces axi_vdma_0/Data_S2MM] [get_bd_addr_segs processing_system7_0/S_AXI_HP0/HP0_DDR_LOWOCM] -force
  assign_bd_address -offset 0x00000000 -range 0x40000000 -target_address_space [get_bd_addr_spaces axi_vdma_1/Data_S2MM] [get_bd_addr_segs processing_system7_0/S_AXI_HP0/HP0_DDR_LOWOCM] -force
  assign_bd_address -offset 0x43C50000 -range 0x00010000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs audio_fft_0/s_axi_control/Reg] -force
  assign_bd_address -offset 0x43000000 -range 0x00010000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs axi_vdma_0/S_AXI_LITE/Reg] -force
  assign_bd_address -offset 0x43010000 -range 0x00010000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs axi_vdma_1/S_AXI_LITE/Reg] -force
  assign_bd_address -offset 0x43C00000 -range 0x00010000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs live_osd_0/s_axi/reg0] -force
  assign_bd_address -offset 0x43C20000 -range 0x00010000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs pcm_buffer_0/s_axi/reg0] -force
  assign_bd_address -offset 0x43C10000 -range 0x00010000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs v_tc_0/ctrl/Reg] -force
  assign_bd_address -offset 0x43C30000 -range 0x00010000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs vision_core_0/s_axi/reg0] -force
  assign_bd_address -offset 0x43C40000 -range 0x00010000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs vision_keys_0/S_AXI/Reg] -force
  assign_bd_address -offset 0x83C50000 -range 0x00010000 -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs z15_fbcsp_0/s_axi_control/Reg] -force
  assign_bd_address -offset 0x00000000 -range 0x40000000 -target_address_space [get_bd_addr_spaces z15_fbcsp_0/Data_m_axi_data] [get_bd_addr_segs processing_system7_0/S_AXI_HP2/HP2_DDR_LOWOCM] -force
  assign_bd_address -offset 0x00000000 -range 0x40000000 -target_address_space [get_bd_addr_spaces z15_fbcsp_0/Data_m_axi_model] [get_bd_addr_segs processing_system7_0/S_AXI_HP2/HP2_DDR_LOWOCM] -force


  # Restore current instance
  current_bd_instance $oldCurInst

  validate_bd_design
  save_bd_design
}
# End of create_root_design()


##################################################################
# MAIN FLOW
##################################################################

create_root_design ""


