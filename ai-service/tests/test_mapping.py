import math

import pytest

from emoji_ai.mapping import decide, normalize_scores


def scores(**changes):
    return {
        "angry": 0.01,
        "disgust": 0.01,
        "fear": 0.01,
        "happy": 0.94,
        "sad": 0.01,
        "surprise": 0.01,
        "neutral": 0.01,
        **changes,
    }


def test_percent_and_probability_same_without_double_softmax():
    probabilities = scores()
    percent = {name: value * 100 for name, value in probabilities.items()}
    a = decide(probabilities, "probability", threshold=0.94)
    b = decide(percent, "percent", threshold=0.94)
    assert a.emoji_type == b.emoji_type == "HAPPY"
    assert a.confidence == pytest.approx(0.94)
    assert b.confidence == pytest.approx(0.94)


@pytest.mark.parametrize(
    "label,emoji",
    [("happy", "HAPPY"), ("sad", "SAD"), ("angry", "ANGRY"), ("surprise", "SURPRISED"), ("neutral", "NEUTRAL")],
)
def test_five_supported_mappings(label, emoji):
    distribution = {name: 0.01 for name in scores()}
    distribution[label] = 0.94
    assert decide(distribution, "probability", threshold=0.9).emoji_type == emoji


@pytest.mark.parametrize("label", ["fear", "disgust"])
def test_unsupported_winner_not_forced_to_neutral(label):
    distribution = {name: 0.01 for name in scores()}
    distribution[label] = 0.94
    result = decide(distribution, "probability", threshold=0.9)
    assert result.emoji_type is None and result.reason == "unsupported_emotion"


def test_logits_numerical_stability_and_aliases():
    result = normalize_scores({name: 10000 + math.log(score) for name, score in scores().items()}, "logits")
    assert result["happy"] == pytest.approx(0.94)
    assert "surprised" in result
    probabilities = scores()
    probabilities["fearful"] = probabilities.pop("fear")
    assert normalize_scores(probabilities, "probability")["fear"] == pytest.approx(0.01)


@pytest.mark.parametrize("value", [True, "0.9", float("nan"), float("inf"), -1, 2])
def test_invalid_scores_are_errors_not_neutral(value):
    with pytest.raises(ValueError):
        normalize_scores(scores(happy=value), "probability")


def test_threshold_and_margin_filters():
    assert decide(scores(), "probability", threshold=0.95).reason == "low_emotion_confidence"
    assert decide(scores(), "probability", threshold=0.9, min_margin=0.95).reason == "ambiguous_emotion"


def test_missing_unknown_labels_and_unnormalized_distribution():
    for distribution in [{}, {**scores(), "unknown": 0}, scores(happy=0.5)]:
        with pytest.raises(ValueError):
            normalize_scores(distribution, "probability")
