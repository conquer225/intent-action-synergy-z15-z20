from pathlib import Path
import shutil
import socket

import vitis


WORKSPACE = r"D:\ican\guardianloop-vitis-2025_2"
XSA = r"D:\ican\guardianloop-z15-2025_2\GuardianLoop_Z15_2025_1\guardianloop_z15_2025_2.xsa"
PLATFORM = "guardianloop_z15_2025_2_platform"
APPLICATION = "guardianloop_eeg_dma_test_2025_2"
CANONICAL_SOURCE = Path(r"D:\ican\ican_fpga_project\software\z15_eeg_uart_rx\src")
APPLICATION_SOURCE = Path(WORKSPACE) / APPLICATION
SOURCE_FILES = (
    "eeg_transport_v0.c",
    "eeg_transport_v0.h",
    "calibration_store_v1.c",
    "calibration_store_v1.h",
    "de_features_v1.c",
    "de_features_v1.h",
    "de_accel_v0.c",
    "de_accel_v0.h",
    "de_calibration_v1.c",
    "de_calibration_v1.h",
    "fatigue_ratio_v0.c",
    "fatigue_ratio_v0.h",
    "hgb_inference_v0.c",
    "hgb_inference_v0.h",
    "hgb_accel_v0.c",
    "hgb_accel_v0.h",
    "guardianloop_eeg_dma_test.c",
)
PLATFORM_BITSTREAM = (
    Path(WORKSPACE)
    / PLATFORM
    / "export"
    / PLATFORM
    / "hw"
    / "guardianloop_z15_2025_2.bit"
)
DEBUG_BITSTREAM = (
    Path(WORKSPACE)
    / APPLICATION
    / "_ide"
    / "bitstream"
    / "guardianloop_z15_2025_2.bit"
)
VIVADO_BITSTREAM = Path(
    r"D:\ican\ican_fpga_project\GuardianLoop_Z15_2025_1"
    r"\GuardianLoop_Z15_2025_1.runs\impl_1\guardianloop_bd_wrapper.bit"
)
USER_CONFIG = APPLICATION_SOURCE / "src" / "UserConfig.cmake"
ENABLE_ARM_GOLDEN_VERIFY = False
ENABLE_ARM_HGB_GOLDEN_VERIFY = False


def reserve_vitis_server_port():
    """Return a free local port and avoid Vitis 2025.2's Windows UTF-8 log bug.

    With port=None, the bundled Vitis Python client reads vitis-server.bat output
    and unconditionally decodes it as UTF-8.  A Chinese Windows code page can
    therefore fail before the client starts.  Supplying an explicit port skips
    that log-parsing path.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


print("Synchronizing canonical Cortex-A9 sources...")
for source_name in SOURCE_FILES:
    shutil.copy2(CANONICAL_SOURCE / source_name, APPLICATION_SOURCE / source_name)
(APPLICATION_SOURCE / "generated").mkdir(parents=True, exist_ok=True)
for source_name in ("hgb_model_data.c", "hgb_model_data.h"):
    shutil.copy2(
        CANONICAL_SOURCE / "generated" / source_name,
        APPLICATION_SOURCE / "generated" / source_name,
    )

# Vitis application sources outside src/ are listed explicitly here.
user_config_text = USER_CONFIG.read_text(encoding="utf-8")
de_driver_entry = '"../de_accel_v0.c"'
calibration_store_entry = '"../calibration_store_v1.c"'
if calibration_store_entry not in user_config_text:
    anchor = '"../eeg_transport_v0.c"'
    if anchor not in user_config_text:
        raise RuntimeError(f"Could not locate source-list anchor in {USER_CONFIG}")
    user_config_text = user_config_text.replace(
        anchor, f'{anchor}\n{calibration_store_entry}', 1
    )
if de_driver_entry not in user_config_text:
    anchor = '"../eeg_transport_v0.c"'
    if anchor not in user_config_text:
        raise RuntimeError(f"Could not locate source-list anchor in {USER_CONFIG}")
    user_config_text = user_config_text.replace(
        anchor, f'{anchor}\n{de_driver_entry}', 1
    )
hgb_driver_entry = '"../hgb_accel_v0.c"'
if hgb_driver_entry not in user_config_text:
    user_config_text = user_config_text.replace(
        de_driver_entry, f'{de_driver_entry}\n{hgb_driver_entry}', 1
    )
hgb_inference_entry = '"../hgb_inference_v0.c"'
hgb_model_entry = '"../generated/hgb_model_data.c"'
for optional_entry in (hgb_inference_entry, hgb_model_entry):
    if ENABLE_ARM_HGB_GOLDEN_VERIFY and optional_entry not in user_config_text:
        user_config_text = user_config_text.replace(
            hgb_driver_entry, f'{hgb_driver_entry}\n{optional_entry}', 1
        )
    elif not ENABLE_ARM_HGB_GOLDEN_VERIFY and optional_entry in user_config_text:
        user_config_text = user_config_text.replace(f"{optional_entry}\n", "", 1)
arm_golden_entry = '"../de_features_v1.c"'
if ENABLE_ARM_GOLDEN_VERIFY and arm_golden_entry not in user_config_text:
    user_config_text = user_config_text.replace(
        de_driver_entry, f'{de_driver_entry}\n{arm_golden_entry}', 1
    )
elif not ENABLE_ARM_GOLDEN_VERIFY and arm_golden_entry in user_config_text:
    user_config_text = user_config_text.replace(f"{arm_golden_entry}\n", "", 1)

arm_verify_definition = '"GL_PL_DE_VERIFY_ARM=1"'
if ENABLE_ARM_GOLDEN_VERIFY and arm_verify_definition not in user_config_text:
    definitions_anchor = "set(USER_COMPILE_DEFINITIONS\n"
    if definitions_anchor not in user_config_text:
        raise RuntimeError(f"Could not locate compile definitions in {USER_CONFIG}")
    user_config_text = user_config_text.replace(
        definitions_anchor,
        f"{definitions_anchor}{arm_verify_definition}\n",
        1,
    )
elif not ENABLE_ARM_GOLDEN_VERIFY and arm_verify_definition in user_config_text:
    user_config_text = user_config_text.replace(
        f"{arm_verify_definition}\n", "", 1
    )
hgb_verify_definition = '"GL_PL_HGB_VERIFY_ARM=1"'
if ENABLE_ARM_HGB_GOLDEN_VERIFY and hgb_verify_definition not in user_config_text:
    definitions_anchor = "set(USER_COMPILE_DEFINITIONS\n"
    if definitions_anchor not in user_config_text:
        raise RuntimeError(f"Could not locate compile definitions in {USER_CONFIG}")
    user_config_text = user_config_text.replace(
        definitions_anchor,
        f"{definitions_anchor}{hgb_verify_definition}\n",
        1,
    )
elif not ENABLE_ARM_HGB_GOLDEN_VERIFY and hgb_verify_definition in user_config_text:
    user_config_text = user_config_text.replace(
        f"{hgb_verify_definition}\n", "", 1
    )
USER_CONFIG.write_text(user_config_text, encoding="utf-8", newline="\n")

vitis_server_port = reserve_vitis_server_port()
print(f"Starting Vitis client on fixed local port {vitis_server_port}...")
client = vitis.create_client(port=vitis_server_port)
try:
    client.set_workspace(path=WORKSPACE)
    platform = client.get_component(name=PLATFORM)
    print("Updating platform hardware specification...")
    print(platform.update_hw(hw_design=XSA))
    print("Building platform and BSP...")
    platform_result = platform.build()
    print(platform_result)
    if platform_result not in (0, None):
        raise RuntimeError(f"Platform build failed with status {platform_result}")
    application = client.get_component(name=APPLICATION)
    print("Building application...")
    application_result = application.build()
    print(application_result)
    if application_result not in (0, None):
        raise RuntimeError(f"Application build failed with status {application_result}")
    bitstream_source = (
        PLATFORM_BITSTREAM if PLATFORM_BITSTREAM.is_file() else VIVADO_BITSTREAM
    )
    if not bitstream_source.is_file():
        raise FileNotFoundError(
            "Bitstream not found in platform export or Vivado implementation: "
            f"{PLATFORM_BITSTREAM}; {VIVADO_BITSTREAM}"
        )
    DEBUG_BITSTREAM.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(bitstream_source, DEBUG_BITSTREAM)
    print(f"Updated debug bitstream: {DEBUG_BITSTREAM}")
finally:
    vitis.dispose()
