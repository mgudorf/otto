"""Process-wide module state: the [science] config and the kernel registry. Hooks get only the store, so they read these."""

from __future__ import annotations

from app.modules.science.kernels import Kernels

config = None           # app.config.Science, set by configure()
kernels = Kernels("")   # replaced by configure()


def configure(science) -> None:
    global config, kernels
    config = science
    kernels = Kernels(science.python)
