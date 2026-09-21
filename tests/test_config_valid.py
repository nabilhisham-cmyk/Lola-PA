"""Pytest wrapper around scripts/validate_config so the config gate runs
locally (pytest) and in CI from the same source of truth."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from validate_config import validate_config  # noqa: E402


def test_config_is_valid():
    errors = validate_config()
    assert not errors, "config.yaml validation errors:\n" + "\n".join(errors)
