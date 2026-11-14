"""Run the teammate's extractors and detector over bounded in-memory browser samples."""

import base64
from datetime import datetime, timezone
from hashlib import file_digest
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
AUDIO_SECONDS = 15
FACE_FRAMES = 20
WIDTH, HEIGHT = 320, 240

ASSETS = {
    "facial": {
        "libreface/AU_Recognition/weights/combined_resnet.pt": "d7d11d9f029afef0d36306f91f5e67fd20531390864ab014e08683dbaca3954b",
        "torch/hub/checkpoints/resnet18-f37072fd.pth": "f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec",
    },
    "speech": {
        "silero/silero_vad.jit": "85c48e1f0ecb604e5d2a268f3ccfb912d4f7e935acdc86af5a3fc5b0aea7b29a",
        "silero/utils_vad.py": "53a55bcf1b642fea9097c2041e44b39eec956953277b78cea1d3e30c697ab5f2",
        "xls-r/config.json": "0bffa0d0e98153e883b828d86491f3c6062cb563dc9d7a9cfd1790da30c286ac",
        "xls-r/pytorch_model.bin": "d5e490574712ad0a6736923b9ed11d4cd51c78609c36205f704fc4e87b11d2e0",
    },
}


def verified_assets(mode):
    for name, expected in ASSETS[mode].items():
        with (MODELS / name).open("rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError(f"Model asset hash mismatch: {name}")


def isolated_environment():
    # Load only the installed wheels and the reviewed adapter snapshot.
    sys.path.extend([str(ROOT / ".venv" / "Lib" / "site-packages"), str(ROOT / "pipeline")])
    os.environ["TORCH_HOME"] = str(MODELS / "torch")
    import torch

    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    return torch


def require_local_weights(_download_id, path):
    if not Path(path).is_file():
        raise FileNotFoundError("Verified LibreFace weights are missing")
    return path


class FacePipeline:
    def __init__(self):
        # Import the AU and alignment submodules without running LibreFace's
        # convenience initializer, which imports unrelated gaze/dlib features.
        spec = importlib.util.find_spec("libreface")
        package = ModuleType("libreface")
        package.__path__ = spec.submodule_search_locations
        package.__spec__ = spec
        sys.modules["libreface"] = package
        from libreface.AU_Recognition import solver_inference_combine
        solver_inference_combine.download_weights = require_local_weights
        from facial.extractor import LibreFaceExtractor
        from facial.windows import WindowAggregator

        self.model = LibreFaceExtractor(device="cpu", weights_download_dir=str(MODELS / "libreface"))
        self.windows = WindowAggregator(FACE_FRAMES)

    def process(self, body, _rate, timestamp):
        import cv2
        import numpy as np

        if len(body) != WIDTH * HEIGHT * 4:
            raise ValueError("Unexpected camera frame size")
        rgba = np.frombuffer(body, dtype=np.uint8).reshape(HEIGHT, WIDTH, 4)
        frame = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        window = self.windows.add_frame(self.model.extract_frame(frame))
        if window is not None:
            window["t"] = timestamp
        return window


class VoicePipeline:
    def __init__(self, torch):
        from speech import features
        from speech.embedding import XLSRecorder

        spec = importlib.util.spec_from_file_location("astra_silero", MODELS / "silero" / "utils_vad.py")
        utils = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(utils)
        features._SILERO_VAD_MODEL = torch.jit.load(str(MODELS / "silero" / "silero_vad.jit"), map_location="cpu").eval()
        features._SILERO_UTILS = (utils.get_speech_timestamps,)
        self.model = XLSRecorder(model_name=str(MODELS / "xls-r"), device="cpu")

    def process(self, body, rate, timestamp):
        from math import gcd
        import numpy as np
        from scipy.signal import resample_poly
        from speech import process_window

        if not isinstance(rate, int) or not 8000 <= rate <= 96000 or len(body) != rate * AUDIO_SECONDS * 4:
            raise ValueError("Unexpected microphone sample size")
        audio = np.frombuffer(body, dtype="<f4")
        if not np.isfinite(audio).all():
            raise ValueError("Nonfinite microphone data")
        if rate != 16000:
            divisor = gcd(16000, rate)
            audio = resample_poly(audio, 16000 // divisor, rate // divisor).astype(np.float32)
        return process_window(audio.copy(), mode="continuous", recorder=self.model, timestamp=timestamp)


def window_output(detector, window):
    result = detector.process_record(window)
    state = result["state"]
    usable = state != "invalid"
    return {
        "t": result["t"], "state": state, "quality": result["quality"], "baseline": result["baseline"],
        "score": result["score"] if usable and state != "calibrating" else None,
        "driftPercentile": result["drift"]["percentile"],
        "contributors": result["contributors"],
        "features": {
            key: float(value) if usable and value is not None and math.isfinite(value) else None
            for key in detector.config.features
            for value in [window["features"].get(key)]
        },
    }


def main():
    # Keep model logs separate from the line-delimited response protocol.
    with os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1) as protocol:
        os.dup2(2, 1)
        mode = sys.argv[1]
        verified_assets(mode)
        torch = isolated_environment()
        from alerting.adapters.facial import get_facial_config
        from alerting.adapters.speech import get_speech_config
        from alerting.core.node import AlertNode
        sys.path.insert(0, str(ROOT))
        from calibration import calibration_version, export_calibration, restore_calibration

        pipeline = FacePipeline() if mode == "facial" else VoicePipeline(torch)
        config = get_facial_config() if mode == "facial" else get_speech_config()
        detector = AlertNode(config, subject_id="local-session")
        print(json.dumps({"kind": "ready", "target": config.calibration_n,
                          "features": config.features}), file=protocol)
        timing = ("rgba-320x240", FACE_FRAMES, 500) if mode == "facial" else ("pcm-f32", AUDIO_SECONDS, 16000)
        version = calibration_version(config, ASSETS[mode], timing)
        embedding_size = len(pipeline.model.au_solver.au_recognition_aus) if mode == "facial" else 1024
        for line in sys.stdin:
            request = json.loads(line)
            command = request.get("command")
            if command:
                reply = {"kind": "control"}
                try:
                    if command == "resume":
                        if mode == "facial":
                            pipeline.windows.buffer.clear()
                    elif command == "save":
                        reply["profile"] = export_calibration(detector, version)
                    elif command == "load":
                        restore_calibration(detector, request.get("profile"), version, embedding_size)
                    else:
                        raise ValueError("Unknown capture action.")
                except (ValueError, TypeError, OverflowError) as error:
                    reply["message"] = str(error)
                print(json.dumps(reply, allow_nan=False), file=protocol)
                continue
            body = base64.b64decode(request["body"], validate=True)
            timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            window = pipeline.process(body, request.get("rate"), timestamp)
            print(json.dumps({"kind": "sample", "window": window_output(detector, window) if window else None},
                             allow_nan=False), file=protocol)


if __name__ == "__main__":
    main()
