"""真实计时的单输入模型 soak；不记录原帧或预测明细，不冒充摄像头长测。"""

import argparse
import json
import math
import time
from collections import Counter, deque
from pathlib import Path

import cv2
import numpy as np
from emoji_ai.adapters import DeepFaceAdapter, LightweightAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["edge", "standard"], required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=7200)
    parser.add_argument("--interval", type=float, default=2)
    args = parser.parse_args()
    if (
        not math.isfinite(args.duration)
        or not 1 <= args.duration <= 86400
        or not math.isfinite(args.interval)
        or not 0.5 <= args.interval <= 60
    ):
        parser.error("Duration [1,86400], interval [0.5,60] seconds")
    frame = cv2.imread(str(args.input))
    if frame is None:
        parser.error("Approved input could not be decoded")
    adapter = (LightweightAdapter if args.profile == "edge" else DeepFaceAdapter)(
        manifest=args.manifest,
        model_dir=args.model_dir,
        detection_threshold=0.85,
    )
    reasons, latencies = Counter(), deque(maxlen=10000)
    started = time.monotonic()
    samples = 0
    while time.monotonic() - started < args.duration:
        tick = time.monotonic()
        observations = adapter.analyze(frame)
        latencies.append((time.monotonic() - tick) * 1000)
        reasons.update([row.reason for row in observations] or ["no_face"])
        samples += 1
        time.sleep(max(0, args.interval - (time.monotonic() - tick)))
    print(
        json.dumps(
            {
                "profile": args.profile,
                "duration_seconds": round(time.monotonic() - started, 3),
                "samples": samples,
                "reasons": dict(reasons),
                "last_10000_latency_ms": {f"p{p}": round(float(np.percentile(latencies, p)), 3) for p in (50, 95, 99)},
                "scope": "single-image model stability; not camera/network/classroom accuracy",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
