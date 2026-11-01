"""Build the QSPI-enabled Z15 application in an isolated Vitis workspace.

This avoids taking the lock held by an open Vitis Unified IDE instance while
still validating the generated XSA, standalone BSP, QSPI driver, and firmware.
"""

from pathlib import Path
import shutil

import vitis


WORKSPACE = Path(r"D:\ican\codex_project\vitis_qspi_verify_20260910_2")
XSA = r"D:\ican\guardianloop-z15-2025_2\GuardianLoop_Z15_2025_1\guardianloop_z15_2025_2.xsa"
CANONICAL = Path(r"D:\ican\ican_fpga_project\software\z15_eeg_uart_rx\src")
REFERENCE_APP = Path(r"D:\ican\guardianloop-vitis-2025_2\guardianloop_eeg_dma_test_2025_2")
PLATFORM_NAME = "guardianloop_qspi_verify_platform"
APP_NAME = "guardianloop_qspi_verify_app"

SOURCE_FILES = (
    "eeg_transport_v0.c",
    "eeg_transport_v0.h",
    "calibration_store_v1.c",
    "calibration_store_v1.h",
    "de_accel_v0.c",
    "de_accel_v0.h",
    "de_calibration_v1.c",
    "de_calibration_v1.h",
    "de_features_v1.h",
    "fatigue_ratio_v0.c",
    "fatigue_ratio_v0.h",
    "hgb_accel_v0.c",
    "hgb_accel_v0.h",
    "hgb_inference_v0.h",
    "guardianloop_eeg_dma_test.c",
)

WORKSPACE.mkdir(parents=True, exist_ok=True)
client = vitis.create_client()
try:
    client.set_workspace(path=str(WORKSPACE))
    platform_root = WORKSPACE / PLATFORM_NAME
    if platform_root.exists():
        platform = client.get_component(name=PLATFORM_NAME)
    else:
        platform = client.create_platform_component(
            name=PLATFORM_NAME,
            hw_design=XSA,
            cpu="ps7_cortexa9_0",
            os="standalone",
            domain_name="standalone_ps7_cortexa9_0",
            template="empty_application",
        )
        print("Building isolated QSPI platform/BSP...")
        if platform.build() not in (0, None):
            raise RuntimeError("Isolated platform build failed")

    platform_xpfm = (
        platform_root / "export" / PLATFORM_NAME / f"{PLATFORM_NAME}.xpfm"
    )
    app = client.create_app_component(
        name=APP_NAME,
        platform=str(platform_xpfm),
        domain="standalone_ps7_cortexa9_0",
        template="empty_application",
    )
    app_root = WORKSPACE / APP_NAME
    for name in SOURCE_FILES:
        shutil.copy2(CANONICAL / name, app_root / name)
    (app_root / "generated").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        CANONICAL / "generated" / "hgb_model_data.h",
        app_root / "generated" / "hgb_model_data.h",
    )
    shutil.copy2(REFERENCE_APP / "src" / "UserConfig.cmake", app_root / "src" / "UserConfig.cmake")
    shutil.copy2(REFERENCE_APP / "src" / "lscript.ld", app_root / "src" / "lscript.ld")

    print("Building isolated QSPI application...")
    if app.build() not in (0, None):
        raise RuntimeError("Isolated application build failed")
    print(f"QSPI_VERIFY_WORKSPACE={WORKSPACE}")
finally:
    vitis.dispose()
