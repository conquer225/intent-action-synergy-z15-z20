"""Offline and board-local entry points. All outputs describe their data source."""
import argparse
import json
import sys
from pathlib import Path
import cv2
import numpy as np
from .training import Dataset, DIMENSIONS, train_mlp, ModelBundle
from .stereo import Calibration, StereoProcessor, write_ply
from .data_tools import prepare_dataset, calibrate_images


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def train(args):
    model, report = train_mlp(Dataset.load(args.dataset), args.task, epochs=args.epochs, seed=args.seed)
    model.save(args.output)
    report["deployable"] = model.deployable
    report["deployment_note"] = "Provenance only; acceptance accuracy and unknown-input tests are still required."
    write_json(Path(args.output)/"metrics.json", report)
    return report


def depth(args):
    calibration = Calibration.load(args.calibration)
    images = [cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) for path in (args.left, args.right)]
    if any(image is None for image in images):
        raise ValueError("cannot read left/right image")
    processor = StereoProcessor(calibration)
    result = processor.process(*images, capture_mode=args.capture_mode, roi=args.roi)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output/"depth.npz", disparity=result.disparity, xyz=result.xyz, valid_mask=result.valid_mask)
    write_ply(output/"cloud.ply", result.xyz[result.valid_mask])
    report = dict(distance_m=result.distance_m, valid=result.distance_m is not None,
                  valid_pixels=int(result.valid_mask.sum()), units="m", capture_mode=args.capture_mode,
                  backend="PS_StereoBM", frames=1)
    write_json(output/"depth.json", report)
    return report


def prepare(args):
    data = prepare_dataset(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    data.save(args.output)
    return dict(samples=len(data.x), dimensions=data.x.shape[1], source=data.source,
                source_kind=data.source_kind, split_by="recording/session group")


def calibrate(args):
    calibration, report = calibrate_images(args.manifest, columns=args.columns, rows=args.rows,
            square_m=args.square_m, capture_mode=args.capture_mode)
    args.output.mkdir(parents=True, exist_ok=True)
    calibration.save(args.output/"calibration.json")
    write_json(args.output/"calibration-report.json", report)
    return report


def fuse(args):
    from .cloud import fuse_clouds, register_open3d
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    clouds, poses = [], []
    for view in manifest["views"]:
        with np.load(args.manifest.parent/view["depth_npz"], allow_pickle=False) as data:
            clouds.append(data["xyz"][data["valid_mask"]])
        poses.append(np.asarray(view["camera_to_world"], float))
    registrations = []
    if args.icp:
        poses, registrations = register_open3d(clouds, poses, voxel_m=args.voxel_m)
    points = fuse_clouds(clouds, poses, voxel_m=args.voxel_m)
    args.output.mkdir(parents=True, exist_ok=True)
    write_ply(args.output/"merged.ply", points)
    report = dict(views=len(clouds), points=len(points), units="m", voxel_m=args.voxel_m,
                  camera_to_world=[p.tolist() for p in poses], registrations=registrations)
    write_json(args.output/"fusion.json", report)
    return report


def audio(args):
    from scipy.io import wavfile
    from scipy.signal import firwin
    from .audio import resample_audio, sound_features, spectrum, DacOutput
    rate, samples = wavfile.read(args.wav)
    if samples.ndim != 1 or samples.dtype not in (np.dtype("int16"), np.dtype("float32")):
        raise ValueError("use mono signed PCM16 or normalized float32 WAV")
    pcm = resample_audio(samples.astype(float)/(32768 if samples.dtype == np.int16 else 1), int(rate))
    if len(pcm) < 16000:
        raise ValueError("at least one second of audio required")
    feature = sound_features(pcm[:16000])
    frequency, amplitude = spectrum(pcm[:1024])
    dac = DacOutput()
    waveform = dac.audio(pcm, fir=firwin(63, 3500, fs=16000) if args.filtered else None)
    scan = dac.scan(amplitude)
    args.output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output/"audio.npz", features=feature, frequency_hz=frequency, amplitude=amplitude,
                        audio_codes=waveform.codes, spectrum_codes=scan.codes, spectrum_sync=scan.sync,
                        output_rate_hz=16000, spectrum_frequency_step_hz=scan.frequency_step_hz)
    report = dict(samples=len(pcm), sample_rate_hz=16000, feature_dimensions=40,
                  peak_hz=float(frequency[np.argmax(amplitude)]), physical_dac_executed=False)
    if args.model:
        model = ModelBundle.load(args.model)
        if model.task != "sound":
            raise ValueError("sound model required")
        prediction = model.predict(feature)
        report.update(class_id=prediction.class_id, valid=prediction.valid, backend=prediction.backend,
                      model_source_kind=model.source_kind)
    write_json(args.output/"audio.json", report)
    return report


def doctor(args):
    from .readiness import inspect_readiness
    board_review = json.loads(args.board_review.read_text(encoding="utf-8")) if args.board_review else {}
    return inspect_readiness(args.models, args.calibration, board_review)


def serve(args):
    import socket
    import time
    from .legacy_eeg import LegacyEEGFeatures
    from .runtime import RuntimeCoordinator
    from .service import BoardSession
    models = {}
    for task in DIMENSIONS:
        path = args.models/task
        if (path/"model.json").is_file():
            model = ModelBundle.load(path)
            if model.task != task or (not model.deployable and not args.allow_synthetic):
                raise ValueError("model task mismatch or synthetic model without --allow-synthetic")
            models[task] = model
    if not models:
        raise ValueError("at least one trained model required")
    runtime = registers = allocator = backend = None
    try:
        if args.backend == 'pl':
            from .linux import UioRegisters, UdmaAllocator
            from .backend import HardwareNPU
            if args.uio is None or args.udmabuf is None:
                raise ValueError('PL backend requires explicit --uio and --udmabuf devices')
            if not 0 < args.npu_timeout <= 60:
                raise ValueError('NPU timeout must be in (0, 60] seconds')
            info = args.uio_sysfs or Path('/sys/class/uio')/args.uio.name/'maps/map0'
            dma_info = args.udmabuf_sysfs or Path('/sys/class/u-dma-buf')/args.udmabuf.name
            registers = UioRegisters(args.uio, info, expected_address=args.npu_base)
            allocator = UdmaAllocator(args.udmabuf, dma_info)
            backend = HardwareNPU(registers, allocator, timeout=args.npu_timeout)
        runtime = RuntimeCoordinator(models=models, eeg_adapter=LegacyEEGFeatures(args.legacy_directory),
                                     backend=backend)
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((args.bind, args.port)); listener.listen(1)
            print(json.dumps(dict(listening=listener.getsockname(), backend=backend.name if backend else "PS_integer_reference",
                                  note="EEG service; vendor camera/ADC/DMA adapters are separate")), file=sys.stderr, flush=True)
            while True:
                connection, address = listener.accept()
                session = BoardSession(connection, runtime)
                try:
                    session.start()
                    while session.pump(): time.sleep(.01)
                finally:
                    session.close()
                    runtime.disconnect_eeg()
    except KeyboardInterrupt:
        return dict(stopped=True, board_probed=False)
    finally:
        if runtime is not None and not runtime.close():
            raise RuntimeError('workers have not stopped; hardware resources retained')
        if backend is not None: backend.close()
        if allocator is not None: allocator.close()
        if registers is not None: registers.close()


def parser():
    root = argparse.ArgumentParser(description="Z15/Z20 compute sidecar; no hardware required for offline commands")
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("train", help="train D-32-3 model from explicit session splits")
    p.add_argument("--task", choices=DIMENSIONS, required=True)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--seed", type=int, default=7)
    p.set_defaults(run=train)
    p = sub.add_parser("depth", help="board-local StereoBM on one calibrated image pair")
    for name in ("calibration", "left", "right", "output"):
        p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--capture-mode", required=True)
    p.add_argument("--roi", nargs=4, type=int)
    p.set_defaults(run=depth)
    p = sub.add_parser("prepare", help="extract image/WAV/EEG/features using explicit session labels")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(run=prepare)
    p = sub.add_parser("calibrate", help="PC offline stereo chessboard calibration")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--columns", type=int, required=True, help="inner corners, not squares")
    p.add_argument("--rows", type=int, required=True)
    p.add_argument("--square-m", type=float, required=True)
    p.add_argument("--capture-mode", required=True)
    p.set_defaults(run=calibrate)
    p = sub.add_parser("fuse", help="PC offline cloud fusion using known camera-to-world poses")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--voxel-m", type=float, default=.005)
    p.add_argument("--icp", action="store_true", help="optional Open3D local refinement; requires overlap and initial guesses")
    p.set_defaults(run=fuse)
    p = sub.add_parser("audio", help="offline one-second sound features, FFT and DAC block generation")
    p.add_argument("--wav", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--filtered", action="store_true")
    p.add_argument("--model", type=Path)
    p.set_defaults(run=audio)
    p = sub.add_parser("doctor", help="read preparation status; never touches a board")
    p.add_argument("--models", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--board-review", type=Path)
    p.set_defaults(run=doctor)
    p = sub.add_parser("serve", help="explicit opt-in EEG TCP compute service; default loopback")
    p.add_argument("--models", type=Path, required=True)
    p.add_argument("--legacy-directory", type=Path)
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9020)
    p.add_argument("--allow-synthetic", action="store_true", help="offline development fixtures only")
    p.add_argument('--backend', choices=['software', 'pl'], default='software')
    p.add_argument('--uio', type=Path)
    p.add_argument('--udmabuf', type=Path)
    p.add_argument('--uio-sysfs', type=Path)
    p.add_argument('--udmabuf-sysfs', type=Path)
    p.add_argument('--npu-base', type=lambda value: int(value, 0), default=0x40000000)
    p.add_argument('--npu-timeout', type=float, default=.5)
    p.set_defaults(run=serve)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = args.run(args)
    except (ValueError, KeyError, OSError, cv2.error) as exc:
        print(json.dumps(dict(error=type(exc).__name__, message=str(exc)), ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
