"""Model registry for per-model API parameters.

Loads ``model_registry.json`` (shipped with the package) and exposes a
lookup function so ``LLMClient`` can resolve the right parameters for
any registered model.  Unknown models get sensible defaults.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

_DEFAULTS: dict[str, Any] = {
    "temperature": 1.0,
    "top_p": 1.0,
    "max_tokens": 16384,
    "extra_params": {},
}


def get_model_params(model: str) -> dict[str, Any]:
    """Return the parameter dict for *model*, falling back to defaults."""
    ref = resources.files(__package__) / "model_registry.json"
    registry = json.loads(ref.read_text(encoding="utf-8"))
    entry = registry.get(model)
    if entry is not None:
        return {**_DEFAULTS, **entry}
    return dict(_DEFAULTS)
