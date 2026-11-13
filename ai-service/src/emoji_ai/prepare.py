"""显式准备获准模型；按清单长度/哈希校验后原子发布，无运行时升级。"""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.request import urlopen


def prepare(manifest_path: Path, model_dir: Path, profile: str):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if profile not in manifest["profiles"]:
        raise ValueError("Unknown model profile")
    root = model_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in manifest["profiles"][profile]["artifacts"]:
        spec = manifest["artifacts"][name]
        target = (root / spec["path"]).resolve()
        if not target.is_relative_to(root) or not spec["url"].startswith("https://"):
            raise ValueError("Invalid model manifest path or URL")
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == spec["sha256"]:
            print(f"{name}: verified")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            digest, size = hashlib.sha256(), 0
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False, suffix=".download") as stream:
                temporary = Path(stream.name)
                with urlopen(spec["url"], timeout=60) as response:
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > spec["bytes"]:
                            raise ValueError(f"Model exceeds manifest size: {name}")
                        digest.update(chunk)
                        stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            if size != spec["bytes"] or digest.hexdigest() != spec["sha256"]:
                raise ValueError(f"Model checksum/size mismatch: {name}")
            os.replace(temporary, target)
            print(f"{name}: prepared and verified")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--profile", choices=["standard", "edge"], required=True)
    args = parser.parse_args()
    prepare(args.manifest, args.model_dir, args.profile)


if __name__ == "__main__":
    main()
