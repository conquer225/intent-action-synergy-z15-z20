"""One bounded hardware check for the existing GuardianLoop PL on PYNQ."""

import json

import numpy as np

from guardianloop_pynq import GuardianLoopPynq, HGB_MODEL_ID


HGB_SELFTEST_FEATURES = np.array([
    -1.0799427238112429, 0.0064851517292395106, -0.5970652500420619,
    -1.5362164348628777, -2.0348449606736621, -0.57838466527657117,
    -0.79645979503565534, -0.0013030056822842734, -0.73281615223406138,
    -1.5662926038036602, 0.62089218734170071, 0.0075000021103507506,
    2.3203663411961548, 0.52859699859961018, -1.4840667145772846,
    -0.53571113350721755, -0.081922129447056707, 9.9376612348268161,
    3.1331495065240853, -1.4684422180831287, -0.71349623319422795,
    0.32832862700636239, 2.4134277225456664, 0.1152285631476298,
    -0.94057100813018668, 0.42538817088899161, 0.80407551693864199,
    6.8397131214581277, 2.859146492403779, -1.4475196711018292,
    -0.62648006525970712, 0.33993655080200291, 2.2544870354040842,
    0.069096737010706274, -0.92757781895071501, -0.60380902037595452,
    0.33232552728770354, 2.1633390262389978, 0.024755580206094124,
    -0.90900518391920526,
], dtype=np.float64)


def main():
    engine = GuardianLoopPynq()
    print(f"overlay_loaded={engine.overlay.is_loaded()}", flush=True)
    print(f"dma_addr=0x{engine.dma.mmio.base_addr:08X} model_id=0x{HGB_MODEL_ID:08X}", flush=True)
    model = engine.predict_features(HGB_SELFTEST_FEATURES)
    print(f"hgb_selftest={json.dumps(model, sort_keys=True)}", flush=True)
    if abs(model["perclos"] - 0.4893543912621553) > 1.0e-6 or model["level"] != 1:
        raise RuntimeError("PL HGB differs from the established bare-metal self-test")

    t = np.arange(2000, dtype=np.float64) / 250.0
    signal = np.rint(500.0 * np.sin(2.0 * np.pi * 10.0 * t)).astype(np.int16)
    window = np.tile(signal[:, None], (1, 8))
    result = engine.process_window(window)
    print(f"eeg_window={json.dumps(result, sort_keys=True)}", flush=True)
    if not result["valid"] or result["state"] != "CALIBRATING" or result["calibration_current"] != 1:
        raise RuntimeError("PL Quality/DE window did not enter calibration")
    if result["valid_mask"] != 0xFF or result["reason_code"] != 0:
        raise RuntimeError("PL Quality reported a non-valid channel")
    print("Z15_PYNQ_GUARDIANLOOP_CORE_OK", flush=True)


if __name__ == "__main__":
    main()
