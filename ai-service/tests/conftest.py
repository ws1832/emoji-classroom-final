from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption("--model-smoke-input", default=None, help="Local approved input for explicit real-model smoke")
    parser.addoption("--model-dir", default=None, help="Directory of checksum-verified prepared models")


@pytest.fixture
def model_smoke_paths(request):
    image = request.config.getoption("--model-smoke-input")
    model_dir = request.config.getoption("--model-dir")
    if not image or not model_dir:
        pytest.skip("Real models require explicit --model-smoke-input and --model-dir")
    return Path(image), Path(model_dir)
