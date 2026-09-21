#!/usr/bin/env python3
"""Inject secrets from the environment into config.yaml at boot.

WHY: the auxiliary lanes (vision, web_extract, compression, ...) inherit their
credentials from ``model.api_key`` in config.yaml. That lookup reads the config
file only and has NO environment fallback, so a key that lives purely in an env
var leaves every aux lane sending an empty bearer token and getting
    401 {"error":{"message":"Unauthorized"}}
The main model does not show the problem, because the provider path reads
OLLAMA_API_KEY from the environment directly.

So the key has to be written into config.yaml. It must never be committed, so
this runs at boot, from the same env var Railway already holds.

Idempotent: re-running with the same value is a no-op, and it never removes a
value it was not given, so a hand-set key is not clobbered.
"""
from __future__ import annotations

import os
import pathlib
import sys

HERMES_HOME = os.environ.get("HERMES_HOME", "/opt/data")
CONFIG = pathlib.Path(HERMES_HOME) / "config.yaml"

# env var -> (dotted config path)
INJECTIONS = {
    "OLLAMA_API_KEY": "model.api_key",
}


def _set(model: dict, path: str, value: str) -> bool:
    keys = path.split(".")
    node = model
    for k in keys[:-1]:
        nxt = node.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            node[k] = nxt
        node = nxt
    if node.get(keys[-1]) == value:
        return False
    node[keys[-1]] = value
    return True


def main() -> int:
    if not CONFIG.is_file():
        print(f"[inject-config-secrets] no config at {CONFIG}, skipping")
        return 0

    import yaml

    try:
        cfg = yaml.safe_load(CONFIG.read_text()) or {}
    except Exception as exc:
        print(f"[inject-config-secrets] config unreadable: {type(exc).__name__}: {exc}")
        return 0

    changed = []
    for env_var, path in INJECTIONS.items():
        value = (os.environ.get(env_var) or "").strip()
        if not value:
            print(f"[inject-config-secrets] {env_var} not set, leaving {path} untouched")
            continue
        if _set(cfg, path, value):
            changed.append(path)

    if not changed:
        print("[inject-config-secrets] nothing to change")
        return 0

    # Preserve the file's existing header comment block by rewriting only the
    # parsed document. PyYAML cannot keep comments, so back up first.
    backup = CONFIG.with_suffix(".yaml.pre-inject")
    if not backup.exists():
        backup.write_text(CONFIG.read_text())

    tmp = CONFIG.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=100))
    os.replace(tmp, CONFIG)
    print(f"[inject-config-secrets] set: {', '.join(changed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
