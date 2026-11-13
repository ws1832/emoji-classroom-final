"""固定模型清单与 SHA-256 校验，推理期间不自动联网下载。"""

import hashlib
import json
from pathlib import Path


def verify_models(manifest_path: Path, model_dir: Path, profile: str) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if profile not in manifest["profiles"]:
        raise ValueError("Unknown model profile")
    result = {}
    root = model_dir.resolve()
    for name in manifest["profiles"][profile]["artifacts"]:
        spec = manifest["artifacts"][name]
        path = (root / spec["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Missing prepared model: {name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != spec["sha256"]:
            raise ValueError(f"Model checksum mismatch: {name}")
        result[name] = path
    return result
