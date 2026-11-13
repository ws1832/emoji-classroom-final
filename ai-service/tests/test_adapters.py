import hashlib
import json

import numpy as np
import pytest

from emoji_ai.adapters import DeepFaceAdapter, _ALIGN_POINTS, alignment_matrix
from emoji_ai.models import verify_models
from emoji_ai.prepare import prepare


def test_alignment_identity_and_scale_translate():
    assert alignment_matrix(_ALIGN_POINTS) == pytest.approx(np.array([[1, 0, 0], [0, 1, 0]]), abs=1e-10)
    transform = alignment_matrix(_ALIGN_POINTS * 2 + [10, 20])
    assert transform == pytest.approx(np.array([[0.5, 0, -5], [0, 0.5, -10]]), abs=1e-10)
    with pytest.raises(ValueError):
        alignment_matrix(np.zeros((5, 2)))


def test_deepface_adapter_uses_emotion_only_and_typed_no_face():
    class NoFace(ValueError):
        pass

    adapter = DeepFaceAdapter.__new__(DeepFaceAdapter)
    adapter.threshold, adapter.min_face, adapter.detection_threshold = 0.7, 48, 0.9
    adapter._no_face = NoFace

    def analyze(frame, **kwargs):
        assert kwargs == {
            "actions": ["emotion"],
            "detector_backend": "yunet",
            "enforce_detection": True,
            "align": True,
            "silent": True,
        }
        return [
            {
                "emotion": {"angry": 1, "disgust": 1, "fear": 1, "happy": 94, "sad": 1, "surprise": 1, "neutral": 1},
                "region": {"w": 100, "h": 100},
                "face_confidence": 0.95,
            }
        ]

    adapter._analyze = analyze
    observation = adapter.analyze(None)[0]
    assert observation.decision.emoji_type == "HAPPY" and observation.decision.confidence == pytest.approx(0.94)
    assert observation.detection_confidence == 0.95

    def failure(frame, **kwargs):
        raise NoFace()

    adapter._analyze = failure
    assert adapter.analyze(None) == []

    def model_failure(frame, **kwargs):
        raise RuntimeError("model failed")

    adapter._analyze = model_failure
    with pytest.raises(RuntimeError):
        adapter.analyze(None)


def test_prepared_models_fail_closed_for_missing_hash_and_path_escape(tmp_path):
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake fixture, not a model")
    manifest = tmp_path / "manifest.json"
    spec = {
        "profiles": {"test": {"artifacts": ["test"]}},
        "artifacts": {"test": {"path": "model.onnx", "sha256": hashlib.sha256(model.read_bytes()).hexdigest()}},
    }
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    assert verify_models(manifest, tmp_path, "test") == {"test": model}
    model.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        verify_models(manifest, tmp_path, "test")
    spec["artifacts"]["test"]["path"] = "../outside.onnx"
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="Missing"):
        verify_models(manifest, tmp_path, "test")


def test_prepare_checksum_failure_does_not_publish_or_leave_partial_file(tmp_path, monkeypatch):
    import io

    content = b"expected model fixture"
    spec = {
        "profiles": {"test": {"artifacts": ["test"]}},
        "artifacts": {
            "test": {
                "path": "model.onnx",
                "url": "https://example.test/model",
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        },
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    model_dir = tmp_path / "models"
    monkeypatch.setattr("emoji_ai.prepare.urlopen", lambda *args, **kwargs: io.BytesIO(b"corrupt model fixture!"))
    with pytest.raises(ValueError, match="checksum"):
        prepare(manifest, model_dir, "test")
    assert list(model_dir.iterdir()) == []
    monkeypatch.setattr("emoji_ai.prepare.urlopen", lambda *args, **kwargs: io.BytesIO(content))
    prepare(manifest, model_dir, "test")
    assert (model_dir / "model.onnx").read_bytes() == content

    def no_network(*args, **kwargs):
        raise AssertionError("A prepared model must not be downloaded again")

    monkeypatch.setattr("emoji_ai.prepare.urlopen", no_network)
    prepare(manifest, model_dir, "test")
