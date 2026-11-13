"""只返回匿名质量/表情结果，不返回图片、人脸坐标或身份信息。"""

import os
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import cv2
import numpy as np

from .mapping import Decision, decide, finite_score
from .models import verify_models

_ZOO_LABELS = ["angry", "disgust", "fearful", "happy", "neutral", "sad", "surprised"]
_ALIGN_POINTS = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float64,
)


@dataclass(frozen=True)
class Observation:
    decision: Decision | None
    detection_confidence: float | None
    reason: str


def alignment_matrix(points):
    """五点非反射 similarity transform，最小二乘而非随机 RANSAC。"""

    source = np.asarray(points, dtype=np.float64)
    if source.shape != (5, 2) or not np.isfinite(source).all():
        raise ValueError("Invalid alignment points")
    x, y = source[:, 0], source[:, 1]
    a = np.zeros((10, 4), dtype=np.float64)
    a[0::2] = np.column_stack([x, -y, np.ones(5), np.zeros(5)])
    a[1::2] = np.column_stack([y, x, np.zeros(5), np.ones(5)])
    if np.linalg.matrix_rank(a) != 4:
        raise ValueError("Degenerate alignment points")
    scale, rotation, tx, ty = np.linalg.lstsq(a, _ALIGN_POINTS.reshape(-1), rcond=None)[0]
    return np.array([[scale, -rotation, tx], [rotation, scale, ty]])


def _validate_options(threshold, detection_threshold, min_face):
    if not 0 <= finite_score(threshold) <= 1 or not 0 < finite_score(detection_threshold) <= 1:
        raise ValueError("Invalid emotion/detection threshold")
    if type(min_face) is not int or min_face < 1:
        raise ValueError("min_face must be a positive integer")


class LightweightAdapter:
    model_version = "opencv-zoo-mobilefacenet-2022july-fp32"
    score_kind = "logits_softmax"

    def __init__(self, *, manifest: Path, model_dir: Path, threshold=0.7, detection_threshold=0.9, min_face=48):
        _validate_options(threshold, detection_threshold, min_face)
        files = verify_models(manifest, model_dir, "edge")
        self.threshold, self.detection_threshold, self.min_face = threshold, detection_threshold, min_face
        self.detector = cv2.FaceDetectorYN.create(str(files["yunet"]), "", (320, 320), detection_threshold, 0.3, 5000)
        self.classifier = cv2.dnn.readNet(str(files["mobilefacenet"]))
        self.classifier.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.classifier.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    def analyze(self, frame):
        self.detector.setInputSize((frame.shape[1], frame.shape[0]))
        _, faces = self.detector.detect(frame)
        if faces is None:
            return []
        observations = []
        for face in faces:
            detection = float(face[-1])
            if not np.isfinite(face).all():
                raise ValueError("Invalid detector output")
            if min(face[2], face[3]) < self.min_face:
                observations.append(Observation(None, detection, "too_small"))
                continue
            # YuNet 五点顺序与官方表情模型对齐模板一致；坐标仅在当前帧内存使用。
            transform = alignment_matrix(face[4:14].reshape(5, 2))
            aligned = cv2.warpAffine(frame, transform, (112, 112))
            rgb = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB).astype(np.float32)
            blob = cv2.dnn.blobFromImage((rgb / 255.0 - 0.5) / 0.5)
            self.classifier.setInput(blob, "data")
            logits = self.classifier.forward("label").reshape(-1)
            if logits.shape != (7,):
                raise ValueError("Unexpected expression output shape")
            decision = decide(dict(zip(_ZOO_LABELS, logits)), "logits", threshold=self.threshold)
            observations.append(Observation(decision, detection, decision.reason))
        return observations


class DeepFaceAdapter:
    model_version = "deepface-emotion-0.0.104-onnx"
    score_kind = "normalized_model_score"

    def __init__(self, *, manifest: Path, model_dir: Path, threshold=0.7, detection_threshold=0.9, min_face=48):
        _validate_options(threshold, detection_threshold, min_face)
        if version("deepface") != "0.0.104":
            raise ValueError("This adapter requires the validated DeepFace 0.0.104 release")
        verify_models(manifest, model_dir, "standard")
        self.threshold, self.detection_threshold, self.min_face = threshold, detection_threshold, min_face
        os.environ["DEEPFACE_HOME"] = str(model_dir.resolve())
        os.environ["DEEPFACE_BACKEND_ENGINE"] = "onnx"
        os.environ["DEEPFACE_ONNX_PROVIDERS"] = "cpu"
        os.environ["yunet_score_threshold"] = str(detection_threshold)
        from deepface import DeepFace
        from deepface.commons.backend_utils import get_backend_engine
        from deepface.modules import modeling
        from deepface.modules.exceptions import FaceNotDetected

        if get_backend_engine() != "onnx":
            raise ValueError("DeepFace backend was initialized differently; use a separate profile process")
        # 两个模型先预热，文件已验证；不运行其他属性或身份模型。
        modeling.build_model(task="facial_attribute", model_name="Emotion")
        modeling.build_model(task="face_detector", model_name="yunet")
        self._analyze = DeepFace.analyze
        self._no_face = FaceNotDetected

    def analyze(self, frame):
        try:
            results = self._analyze(
                frame,
                actions=["emotion"],
                detector_backend="yunet",
                enforce_detection=True,
                align=True,
                silent=True,
            )
        except self._no_face:
            return []
        observations = []
        for row in results:
            region = row["region"]
            detection = row.get("face_confidence")
            detection = float(detection) if detection is not None else None
            if detection is not None and (not np.isfinite(detection) or not 0 <= detection <= 1):
                raise ValueError("Invalid detector confidence")
            if min(region["w"], region["h"]) < self.min_face:
                observations.append(Observation(None, detection, "too_small"))
                continue
            if detection is not None and detection < self.detection_threshold:
                observations.append(Observation(None, detection, "low_detection_confidence"))
                continue
            decision = decide(row["emotion"], "percent", threshold=self.threshold)
            observations.append(Observation(decision, detection, decision.reason))
        return observations
