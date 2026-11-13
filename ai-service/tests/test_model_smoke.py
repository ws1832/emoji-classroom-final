"""人工显式启用的真实模型测试；只验证可推理，不测标签准确率。"""

import cv2
import numpy as np
import pytest

from emoji_ai.adapters import DeepFaceAdapter, LightweightAdapter
from emoji_ai.mapping import EMOJIS


@pytest.mark.model_smoke
@pytest.mark.parametrize("factory", [DeepFaceAdapter, LightweightAdapter])
def test_prepared_models_infer_offline_and_blank_has_no_observation(factory, model_smoke_paths, monkeypatch):
    image, model_dir = model_smoke_paths
    # 环境已经安装；模型文件事先准备。任何隐式权重下载均立即失败。
    if factory is DeepFaceAdapter:
        monkeypatch.setenv("DEEPFACE_HOME", str(model_dir.resolve()))
        monkeypatch.setenv("DEEPFACE_BACKEND_ENGINE", "onnx")
        monkeypatch.setenv("DEEPFACE_ONNX_PROVIDERS", "cpu")
        from deepface.commons import weight_utils

        original = weight_utils.download_weights_if_necessary

        def offline(file_name, source_url, compress_type=None):
            expected = model_dir / ".deepface" / "weights" / file_name
            assert expected.is_file(), "Implicit model download is prohibited"
            return original(file_name, source_url, compress_type)

        monkeypatch.setattr(weight_utils, "download_weights_if_necessary", offline)
    adapter = factory(manifest=model_dir / "manifest.json", model_dir=model_dir, detection_threshold=0.85)
    frame = cv2.imread(str(image))
    assert frame is not None
    observations = adapter.analyze(frame)
    assert observations, "Approved face smoke input must produce an actual detection"
    assert any(row.decision and row.decision.emoji_type in EMOJIS for row in observations)
    for row in observations:
        assert row.decision is None or 0 <= row.decision.confidence <= 1
        assert row.detection_confidence is None or 0 <= row.detection_confidence <= 1
        assert set(vars(row)) == {"decision", "detection_confidence", "reason"}
    assert adapter.analyze(np.zeros((480, 640, 3), dtype=np.uint8)) == []
