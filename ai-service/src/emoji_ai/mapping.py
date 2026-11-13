"""模型分数规范化和五类映射，独立于模型引擎及网络。"""

import math
from dataclasses import dataclass
from numbers import Real
from typing import Literal, Mapping

MAPPING_VERSION = "five-emotions-v1"
EMOJIS = frozenset({"HAPPY", "SAD", "ANGRY", "SURPRISED", "NEUTRAL"})
_ALIASES = {"surprise": "surprised", "fearful": "fear"}
_LABELS = frozenset({"happy", "sad", "angry", "surprised", "neutral", "fear", "disgust"})
_MAPPING = {"happy": "HAPPY", "sad": "SAD", "angry": "ANGRY", "surprised": "SURPRISED", "neutral": "NEUTRAL"}


@dataclass(frozen=True)
class Decision:
    emoji_type: str | None
    confidence: float
    label: str
    reason: str


def finite_score(value) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError("Model scores must be finite numbers")
    return float(value)


def normalize_scores(
    scores: Mapping[str, float], kind: Literal["probability", "percent", "logits"]
) -> dict[str, float]:
    if kind not in {"probability", "percent", "logits"} or len(scores) != 7:
        raise ValueError("Use an explicit score kind and all seven emotion labels")
    result = {}
    for label, raw in scores.items():
        name = _ALIASES.get(label.lower(), label.lower())
        if name not in _LABELS or name in result:
            raise ValueError("Unknown or duplicate emotion label")
        result[name] = finite_score(raw)
    if kind == "logits":
        maximum = max(result.values())
        result = {label: math.exp(score - maximum) for label, score in result.items()}
        total = sum(result.values())
        return {label: score / total for label, score in result.items()}
    scale = 100.0 if kind == "percent" else 1.0
    if any(score < 0 or score > scale + 1e-5 for score in result.values()):
        raise ValueError("Scores do not match the configured score kind")
    total = sum(result.values())
    if not math.isclose(total, scale, rel_tol=1e-4, abs_tol=1e-5):
        raise ValueError("Model distribution is not normalized")
    # 仅消除浮点舍入误差，不重新解释概率或给 percentage 再做 softmax。
    return {label: score / total for label, score in result.items()}


def decide(
    scores: Mapping[str, float],
    kind: Literal["probability", "percent", "logits"],
    *,
    threshold: float,
    min_margin: float = 0.0,
) -> Decision:
    threshold, min_margin = finite_score(threshold), finite_score(min_margin)
    if not 0 <= threshold <= 1 or not 0 <= min_margin <= 1:
        raise ValueError("Threshold and margin must be in [0,1]")
    normalized = normalize_scores(scores, kind)
    ranked = sorted(normalized.items(), key=lambda row: (-row[1], row[0]))
    label, confidence = ranked[0]
    if label not in _MAPPING:
        return Decision(None, confidence, label, "unsupported_emotion")
    if confidence < threshold:
        return Decision(None, confidence, label, "low_emotion_confidence")
    if confidence - ranked[1][1] < min_margin:
        return Decision(None, confidence, label, "ambiguous_emotion")
    return Decision(_MAPPING[label], confidence, label, "accepted")
