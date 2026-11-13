"""离线模型 doctor/benchmark。这里只验证模型，不冒充完整采集 worker。"""

import argparse
import json
import math
import platform
import time
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import cv2
import numpy as np

from .adapters import DeepFaceAdapter, LightweightAdapter


def benchmark(adapter, frames, *, warmup=2, repeats=10):
    for _ in range(warmup):
        for frame in frames:
            adapter.analyze(frame)
    durations, reasons, faces = [], Counter(), 0
    for _ in range(repeats):
        for frame in frames:
            started = time.perf_counter()
            observations = adapter.analyze(frame)
            durations.append((time.perf_counter() - started) * 1000)
            if not observations:
                reasons["no_face"] += 1
            faces += len(observations)
            reasons.update(row.reason for row in observations)
    return {
        "samples": len(durations),
        "faces": faces,
        "reasons": dict(reasons),
        "warm_latency_ms": {f"p{p}": round(float(np.percentile(durations, p)), 3) for p in (50, 95, 99)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["doctor", "benchmark"])
    parser.add_argument("--profile", choices=["standard", "edge"], required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--detection-threshold", type=float, default=0.9)
    args = parser.parse_args()
    if (
        not 1 <= args.repeats <= 10000
        or not math.isfinite(args.threshold)
        or not 0 <= args.threshold <= 1
        or not math.isfinite(args.detection_threshold)
        or not 0 < args.detection_threshold <= 1
    ):
        parser.error("Use repeats in [1,10000], threshold in [0,1], detection-threshold in (0,1]")
    started = time.perf_counter()
    factory = DeepFaceAdapter if args.profile == "standard" else LightweightAdapter
    adapter = factory(
        manifest=args.manifest,
        model_dir=args.model_dir,
        threshold=args.threshold,
        detection_threshold=args.detection_threshold,
    )
    report = {
        "profile": args.profile,
        "model_version": adapter.model_version,
        "score_kind": adapter.score_kind,
        "threshold": args.threshold,
        "detection_threshold": args.detection_threshold,
        "startup_ms": round((time.perf_counter() - started) * 1000, 3),
        "environment": {
            "python": platform.python_version(),
            "os": platform.system(),
            "opencv": version("opencv-contrib-python-headless"),
            "numpy": version("numpy"),
        },
    }
    if args.command == "benchmark":
        if not args.input:
            parser.error("benchmark requires at least one --input")
        frames = [cv2.imread(str(path)) for path in args.input]
        if any(frame is None for frame in frames):
            parser.error("An input image could not be decoded")
        report.update(benchmark(adapter, frames, repeats=args.repeats))
        # 始终验证无脸帧；不把异常吞掉或把它伪装成 NEUTRAL。
        report["blank_frame_faces"] = len(adapter.analyze(np.zeros((480, 640, 3), dtype=np.uint8)))
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
