"""Process-wide module state: the [science] config, the kernel registry and the scripts running now. Hooks get only the store, so they read these."""

from __future__ import annotations

from typing import Any

from app.modules.science.kernels import Kernels

config = None                    # app.config.Science, set by configure()
kernels = Kernels("")            # replaced by configure()
scripts: dict[str, Any] = {}     # file id -> the subprocess of a script running now


def configure(science) -> None:
    global config, kernels
    config = science
    kernels = Kernels(science.python)
    scripts.clear()
