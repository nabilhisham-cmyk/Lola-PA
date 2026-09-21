#!/usr/bin/env python3
"""Validate config.yaml before it can ship to Railway.

Catches the class of bug that took the bot down on 2026-06-27: a config with
no usable model/provider block (which makes Hermes fall back to a default model
that ollama-cloud doesn't host -> "model provider failure"). Run in CI and via
pytest; exits non-zero with a clear message on any error.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"

# Providers Hermes knows how to route. Unknown values warn (forward-compat with
# new upstream providers) but a *missing/empty* provider is a hard error.
KNOWN_PROVIDERS = {
    "ollama-cloud", "ollama", "openrouter", "anthropic", "openai", "custom",
    "bedrock", "azure-foundry", "novita", "glm", "qwen", "nous",
}


def validate_config(path: Path = CONFIG_PATH) -> list[str]:
    """Return a list of error strings. Empty list == valid."""
    errors: list[str] = []

    if not path.exists():
        return [f"config.yaml not found at {path}"]

    try:
        cfg = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        return [f"config.yaml is not valid YAML: {exc}"]

    if not isinstance(cfg, dict):
        return ["config.yaml did not parse to a mapping"]

    model = cfg.get("model")
    if not isinstance(model, dict):
        errors.append("missing 'model:' block")
        return errors  # nothing else worth checking

    default = model.get("default")
    if not isinstance(default, str) or not default.strip():
        errors.append("model.default is missing or empty")

    provider = model.get("provider")
    if not isinstance(provider, str) or not provider.strip():
        errors.append("model.provider is missing or empty")
    elif provider not in KNOWN_PROVIDERS:
        print(f"::warning::model.provider '{provider}' is not in the known set "
              f"{sorted(KNOWN_PROVIDERS)} — proceeding, but double-check it.")

    base_url = model.get("base_url")
    if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
        errors.append("model.base_url is missing or not an http(s) URL")

    # Fallback chain (optional, but if present each entry must be usable).
    for i, fb in enumerate(cfg.get("fallback_providers") or []):
        if not isinstance(fb, dict) or not fb.get("provider") or not fb.get("model"):
            errors.append(f"fallback_providers[{i}] must have both 'provider' and 'model'")

    # Each profile dir should have a SOUL.md so personas don't load empty.
    profiles_dir = path.parent / "profiles"
    if profiles_dir.is_dir():
        for p in sorted(profiles_dir.iterdir()):
            if p.is_dir() and not (p / "SOUL.md").exists():
                errors.append(f"profile '{p.name}' has no SOUL.md")

    return errors


def main() -> int:
    errors = validate_config()
    if errors:
        print("config.yaml validation FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("config.yaml validation passed "
          "(model.default / provider / base_url present, profiles OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
